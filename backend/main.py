import os

import chromadb
import requests
from config import settings
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="RAG API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
collection = client.get_or_create_collection(
    settings.COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
)

DOCS_DIR = settings.DOCS_DIRECTORY


def ingest_docs():
    """Load every .txt file in docs/ into the collection (idempotent via upsert)."""
    ids, texts = [], []
    for name in sorted(os.listdir(DOCS_DIR)):
        if name.endswith(".txt"):
            with open(os.path.join(DOCS_DIR, name), encoding="utf-8") as f:
                text = f.read().strip()
            if text:
                ids.append(name)
                texts.append(text)
    if ids:
        collection.upsert(ids=ids, documents=texts, metadatas=[{"source": i} for i in ids])
    return len(ids)


@app.on_event("startup")
def load_docs_on_startup():
    ingest_docs()


@app.post("/ingest")
def ingest():
    return {"ingested": ingest_docs(), "documents": collection.count()}


@app.get("/health")
def health():
    ollama_ok = False
    try:
        r = requests.get(f"{settings.OLLAMA_URL}/api/tags", timeout=3)
        ollama_ok = r.status_code == 200
    except requests.RequestException:
        ollama_ok = False
    return {
        "status": "healthy",
        "ollama": "connected" if ollama_ok else "unavailable",
        "ollama_url": settings.OLLAMA_URL,
        "documents": collection.count(),
    }


@app.get("/")
def root():
    return {"message": "RAG API running in Docker", "model": settings.MODEL_NAME}


class AskRequest(BaseModel):
    question: str


@app.post("/ask")
def ask(req: AskRequest):
    results = collection.query(
        query_texts=[req.question], n_results=max(1, settings.MAX_RESULTS)
    )
    docs = results["documents"][0] if results["documents"] else []
    metas = results["metadatas"][0] if results["metadatas"] else []
    dists = results["distances"][0] if results["distances"] else []
    sources = [
        {"source": m.get("source", "unknown"), "distance": d, "text": t}
        for t, m, d in zip(docs, metas, dists)
        if d <= settings.CONFIDENCE_THRESHOLD
    ]
    context = "\n\n".join(s["text"] for s in sources)
    if context:
        prompt = (
            "Answer the question using only the context below. "
            "If the answer is not in the context, say you don't know.\n\n"
            f"Context:\n{context}\n\nQuestion: {req.question}\nAnswer:"
        )
    else:
        prompt = req.question
    try:
        r = requests.post(
            f"{settings.OLLAMA_URL}/api/generate",
            json={"model": settings.MODEL_NAME, "prompt": prompt, "stream": False},
            timeout=300,
        )
        r.raise_for_status()
        answer = r.json().get("response", "")
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Ollama error: {e}") from e
    confidence = "none" if not sources else "high" if sources[0]["distance"] < 0.5 else "medium"
    return {"answer": answer, "sources": sources, "confidence": confidence}
