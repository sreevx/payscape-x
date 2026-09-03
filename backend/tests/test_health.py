"""Tests for /health and /api/v1/health."""

from fastapi.testclient import TestClient

from app.core import database
from app.main import create_app


class _BrokenEngine:
    """Engine stand-in whose connect() always fails."""

    def connect(self):
        raise ConnectionError("database is down")


def _client(db_engine=None, monkeypatch=None):
    app = create_app()
    if db_engine is not None and monkeypatch is not None:
        monkeypatch.setattr(database, "get_engine", lambda: db_engine)
    return TestClient(app)


def test_health_root_endpoint(db_engine, monkeypatch):
    client = _client(db_engine, monkeypatch)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "payscape-x",
        "version": "0.1.0",
        "database": "ok",
    }


def test_health_api_v1_endpoint(db_engine, monkeypatch):
    client = _client(db_engine, monkeypatch)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "payscape-x"
    assert body["database"] == "ok"


def test_health_reports_database_unavailable(db_engine, monkeypatch):
    """When the DB is down the API stays honest: status ok, database unavailable."""
    monkeypatch.setattr(database, "get_engine", lambda: _BrokenEngine())
    client = TestClient(create_app())

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "unavailable"


def test_cors_allows_configured_frontend_origin(db_engine, monkeypatch):
    client = _client(db_engine, monkeypatch)
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin")
        == "http://localhost:3000"
    )


def test_cors_blocks_unknown_origin(db_engine, monkeypatch):
    client = _client(db_engine, monkeypatch)
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "https://evil.example.com"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers