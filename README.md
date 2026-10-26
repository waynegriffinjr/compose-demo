# compose-demo

A minimal RAG (Retrieval-Augmented Generation) starter deployed with Docker Compose. A FastAPI backend stores documents in ChromaDB and answers questions through a local Ollama LLM server, with a Streamlit chat UI, all running in containers.

## Architecture

| Service   | Image / Build      | Port  | Purpose                                              |
|-----------|--------------------|-------|------------------------------------------------------|
| `backend` | built from `./backend` | 8000 | FastAPI app + ChromaDB (persistent vector store)  |
| `frontend`| built from `./frontend` | 8501 | Streamlit chat UI (talks to `backend`)           |
| `ollama`  | `ollama/ollama`    | 11434 | Local LLM server                                     |

Volumes:
- `chroma_data` → `/app/chroma_data` (vector DB persists across restarts)
- `ollama_data` → `/root/.ollama` (downloaded models persist)

The backend reaches Ollama at `http://ollama:11434` via Compose's internal network.

## Project structure

```
COMPOSE-DEMO/
├── docker-compose.yml
├── .env                   # real local settings (git/docker-ignored)
├── .env.example           # committed template
├── README.md
├── frontend/
│   ├── Dockerfile
│   ├── app.py             # Streamlit chat UI
│   └── requirements.txt
└── backend/
    ├── Dockerfile
    ├── config.py          # centralized Settings
    ├── main.py            # FastAPI app
    ├── requirements.txt
    └── docs/              # .txt files ingested at startup
        └── sample.txt
```

## Prerequisites

- Docker Desktop (or another Docker engine) **running**
- Docker Compose v2 (`docker-compose` or `docker compose`)

## Quick start

```bash
# 0. Create your local config (first time only)
cp .env.example .env

# 1. Build and start everything
docker-compose up --build

# 2. In another terminal, pull the model (first time only)
docker-compose exec ollama ollama pull llama3.2:1b

# 3. Verify
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"healthy","ollama":"connected","ollama_url":"http://ollama:11434","documents":1}
```

Chat UI: http://localhost:8501 (the model must be pulled first, see step 2)

Interactive API docs: http://localhost:8000/docs

## Configuration

All settings are centralized in `backend/config.py` (a `Settings` class) and read from environment variables. Docker Compose loads them into the `backend` container from `.env` via `env_file: .env`.

Setup:

```bash
cp .env.example .env    # then edit .env with your own values
```

- `.env` holds your real local values and is git-ignored and Docker-ignored (never committed or baked into the image).
- `.env.example` is the committed template with safe placeholder values.

| Variable               | Default (in `config.py`) | Description                                   |
|------------------------|--------------------------|-----------------------------------------------|
| `OLLAMA_URL`           | `http://localhost:11434` | Ollama server URL (`http://ollama:11434` in Compose) |
| `MODEL_NAME`           | `llama3.2:1b`            | Ollama model name                             |
| `CHROMA_PATH`          | `./chroma_data`          | ChromaDB persistence directory                |
| `COLLECTION_NAME`      | `documents`              | ChromaDB collection name                      |
| `MAX_RESULTS`          | `3`                      | Number of documents to retrieve               |
| `CONFIDENCE_THRESHOLD` | `1.2`                    | Retrieval distance threshold                  |
| `DEBUG`                | `false`                  | Print the loaded config at startup when `true` |
| `DOCS_DIRECTORY`       | `./docs`                 | Directory of `.txt` files to ingest           |
| `OPENAI_API_KEY`       | *(empty)*                | Optional cloud fallback key (keep in `.env` only) |

To change a value, edit `.env` and recreate the container (a plain restart does not reload `.env`):

```bash
docker compose up -d backend
curl http://localhost:8000/    # "model" reflects MODEL_NAME
```

If you change `MODEL_NAME`, pull the model too: `docker compose exec ollama ollama pull <model>`.

## API endpoints

| Method | Path       | Description                                                        |
|--------|------------|--------------------------------------------------------------------|
| GET    | `/`        | Basic status message and configured model                          |
| GET    | `/health`  | Backend status, Ollama connectivity, and document count            |
| POST   | `/ask`     | Body `{"question": "..."}`. Retrieves matching chunks from ChromaDB, asks Ollama, returns `answer`, `sources`, `confidence` |
| POST   | `/ingest`  | Re-load all `backend/docs/*.txt` files into ChromaDB (upsert)      |

## Adding documents

1. Drop `.txt` files into `backend/docs/`.
2. Rebuild so they are copied into the image: `docker-compose up --build -d`.
3. Documents are ingested automatically at startup (or call `POST /ingest`). Ingestion uses upsert keyed by filename, so re-running does not create duplicates.

Check the count with `curl http://localhost:8000/health`.

## Common commands

```bash
docker-compose up -d --build        # start in background
docker-compose logs -f backend      # follow backend logs
docker-compose ps                   # service status
docker-compose down                 # stop containers (keeps volumes)
docker-compose down -v              # stop and delete volumes (wipes DB and models)
docker-compose build --no-cache backend   # force a clean backend rebuild
```

## Troubleshooting

- **`failed to connect to the docker API ... docker.sock`** – Docker isn't running. Start Docker Desktop (`open -a Docker`) and wait until it's ready (`docker info`).
- **`np.float_ was removed in the NumPy 2.0 release`** – `chromadb==0.4.22` needs `numpy<2`. This is pinned in `requirements.txt`; rebuild with `--no-cache` if you see a stale image.
- **`get_or_create_collection() got an unexpected keyword argument 'configuration'`** – that argument exists only in newer ChromaDB. With 0.4.x use `metadata={"hnsw:space": "cosine"}` (as `main.py` does).
- **`ERR_CONNECTION_REFUSED` on localhost:8000** – the backend crashed or isn't up. Check `docker-compose logs backend`.
- **`documents: 0` in `/health`** – ensure `.txt` files exist in `backend/docs/`, rebuild, or call `POST /ingest`.
- **`ollama: unavailable`** – confirm the `ollama` container is running and the model is pulled.
- **`POST /ask` returns 404** – you are running an old backend image; rebuild with `docker-compose up -d --build`.
- **`/ask` returns 502 "Ollama error"** – the model isn't pulled or Ollama is down: `docker-compose exec ollama ollama pull llama3.2:1b`.
- **Answer is "I don't know"** – no document matched closely enough (see `CONFIDENCE_THRESHOLD`); add relevant `.txt` files to `backend/docs/`.
- **"Failed to send telemetry event"** – harmless log noise from the pinned ChromaDB version.

## Notes

- The first backend start downloads Chroma's default embedding model (~79 MB) into the container; it is re-downloaded if the container is recreated.
- CORS is open (`*`) for demo purposes; restrict it for production.
- `/ask` is non-streaming; the first answer can be slow while Ollama loads the model.
