import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_root_returns_200():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "model" in data


def test_health_returns_200_with_expected_fields():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "ollama" in data
    assert "documents" in data


def test_stats_returns_200_with_document_count():
    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert "document_count" in data
    assert isinstance(data["document_count"], int)
