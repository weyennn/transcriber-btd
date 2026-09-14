import importlib
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


def test_delete_history_folder_requires_valid_result_folder(monkeypatch):
    monkeypatch.setenv("DATA_DIR", tempfile.mkdtemp(prefix="transcribe-delete-test-"))
    import src.utils.paths as paths
    importlib.reload(paths)
    import src.core.engine as engine
    monkeypatch.setattr(engine.TranscribeEngine, "apply_wdac_patch", classmethod(lambda cls: None))
    import src.web.server as server
    importlib.reload(server)
    client = TestClient(server.app)

    response = client.delete("/api/history/not-valid")
    assert response.status_code == 400


def test_delete_history_folder_removes_only_target_folder(monkeypatch):
    monkeypatch.setenv("DATA_DIR", tempfile.mkdtemp(prefix="transcribe-delete-test-"))
    import src.utils.paths as paths
    importlib.reload(paths)
    import src.core.engine as engine
    monkeypatch.setattr(engine.TranscribeEngine, "apply_wdac_patch", classmethod(lambda cls: None))
    import src.web.server as server
    importlib.reload(server)
    client = TestClient(server.app)

    target = server.HASIL_DIR / "01_delete-me"
    sibling = server.HASIL_DIR / "02_keep-me"
    target.mkdir(parents=True)
    sibling.mkdir(parents=True)
    (target / "transkrip.txt").write_text("hapus", encoding="utf-8")
    (sibling / "transkrip.txt").write_text("tetap", encoding="utf-8")

    response = client.delete("/api/history/01_delete-me")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "deleted": "01_delete-me"}
    assert not target.exists()
    assert sibling.exists()
