"""Focused regression tests for backend-owned user storage namespaces."""
import importlib
from pathlib import Path

import pytest
from fastapi import HTTPException


def _reload_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import src.utils.paths as paths
    return importlib.reload(paths)


def _reload_server(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import src.utils.paths as paths
    importlib.reload(paths)
    import src.web.auth as auth
    importlib.reload(auth)
    import src.core.engine as engine
    monkeypatch.setattr(engine.TranscribeEngine, "apply_wdac_patch", classmethod(lambda cls: None))
    import src.web.server as server
    return importlib.reload(server)


def test_user_storage_roots_are_isolated_but_legacy_stays_compatible(monkeypatch, tmp_path):
    paths = _reload_paths(monkeypatch, tmp_path)

    assert paths.upload_dir_for("legacy") == paths.UPLOAD_DIR
    assert paths.result_dir_for("legacy") == paths.HASIL_DIR
    assert paths.upload_dir_for("a" * 64) == paths.UPLOAD_DIR / ("a" * 64)
    assert paths.result_dir_for("b" * 64) == paths.HASIL_DIR / ("b" * 64)
    with pytest.raises(ValueError):
        paths.result_dir_for("../other-user")


def test_history_and_file_resolution_cannot_cross_user_namespaces(monkeypatch, tmp_path):
    server = _reload_server(monkeypatch, tmp_path)
    alice = {"sub": "alice", "email": "alice@example.test"}
    bob = {"sub": "bob", "email": "bob@example.test"}
    alice_id = server._owner_id(alice)
    bob_id = server._owner_id(bob)
    alice_folder = server.result_dir_for(alice_id) / "01_alice"
    bob_folder = server.result_dir_for(bob_id) / "01_bob"
    alice_folder.mkdir(parents=True)
    bob_folder.mkdir(parents=True)
    (alice_folder / "transkrip.txt").write_text("alice only", encoding="utf-8")
    (bob_folder / "transkrip.txt").write_text("bob only", encoding="utf-8")

    assert server.history(alice)["items"] == [{"name": "01_alice", "files": ["transkrip.txt"]}]
    with pytest.raises(HTTPException) as exc:
        server.history_file("01_bob", "transkrip.txt", _user=alice)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        server._result_folder_for_user("../01_bob", alice_id)
    assert exc.value.status_code == 400


def test_history_file_accepts_result_folder_with_dots(monkeypatch, tmp_path):
    server = _reload_server(monkeypatch, tmp_path)
    user = {"dev": True}
    folder = server.HASIL_DIR / "03_WhatsApp Audio 2026-09-25 at 11.12.27-4"
    folder.mkdir(parents=True)
    (folder / "transkrip.txt").write_text("hasil aman", encoding="utf-8")

    response = server.history_file(folder.name, "transkrip.txt", _user=user)

    assert response == {"name": "transkrip.txt", "content": "hasil aman", "size": 10}


def test_legacy_archive_is_not_visible_to_users_without_admin_allowlist(monkeypatch, tmp_path):
    monkeypatch.delenv("AUTH_ADMIN_EMAILS", raising=False)
    server = _reload_server(monkeypatch, tmp_path)
    user = {"sub": "user", "email": "user@ugm.ac.id"}
    with pytest.raises(HTTPException) as exc:
        server.legacy_archive(user)
    assert exc.value.status_code == 403


def test_job_routes_pass_owner_to_every_job_lookup(monkeypatch, tmp_path):
    server = _reload_server(monkeypatch, tmp_path)
    user = {"sub": "alice", "email": "alice@example.test"}
    expected_owner = server._owner_id(user)
    calls = []

    class FakeJob:
        def to_dict(self):
            return {"id": "job-1"}

    class FakeJobs:
        def active(self, owner_id):
            calls.append(("active", owner_id))
            return []

        def get(self, job_id, owner_id):
            calls.append(("get", job_id, owner_id))
            return FakeJob()

        def cancel(self, job_id, owner_id):
            calls.append(("cancel", job_id, owner_id))
            return True

        def event_stream(self, job_id, owner_id):
            calls.append(("stream", job_id, owner_id))
            return iter(())

    server.jobs = FakeJobs()
    assert server.active_jobs(user) == {"items": []}
    assert server.job_status("job-1", user) == {"id": "job-1"}
    assert server.job_cancel("job-1", user) == {"ok": True}
    response = server.job_stream("job-1", user)
    assert response.status_code == 200
    assert calls == [
        ("active", expected_owner),
        ("get", "job-1", expected_owner),
        ("cancel", "job-1", expected_owner),
        ("get", "job-1", expected_owner),
        ("stream", "job-1", expected_owner),
    ]
