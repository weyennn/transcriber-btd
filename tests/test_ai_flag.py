"""Test feature flag AI_ENABLED pada server (Docker deployment)."""
import importlib
import os


def _make_client(monkeypatch, ai_enabled):
    monkeypatch.setenv("AI_ENABLED", ai_enabled)
    import src.web.server as server
    importlib.reload(server)
    from fastapi.testclient import TestClient
    return TestClient(server.app)


def test_env_expose_ai_enabled_off(monkeypatch):
    client = _make_client(monkeypatch, "false")
    r = client.get("/api/env")
    assert r.status_code == 200
    assert r.json()["ai_enabled"] is False


def test_env_expose_ai_enabled_on(monkeypatch):
    client = _make_client(monkeypatch, "true")
    r = client.get("/api/env")
    assert r.json()["ai_enabled"] is True


def test_notulen_ai_503_saat_off(monkeypatch):
    client = _make_client(monkeypatch, "false")
    r = client.post("/api/notulen/ai", json={"output_dir": "01_test"})
    assert r.status_code == 503
    assert "dimatikan" in r.json()["detail"]
