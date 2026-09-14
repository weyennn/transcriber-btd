import importlib
import json


def test_job_store_persists_and_marks_running_interrupted(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    import src.web.job_store as store
    store = importlib.reload(store)
    store.init()

    class Job:
        id = "abc123"
        kind = "transcribe"
        audio_path = "/data/uploads/a.mp3"
        config = {"model": "medium"}
        status = "pending"

    store.create(Job())
    assert store.active()[0]["id"] == "abc123"
    store.update(Job(), status="running", progress=42, message="Memuat model")
    assert store.get("abc123")["status"] == "running"

    store.init()
    assert store.active() == []
    row = store.get("abc123")
    assert row["status"] == "interrupted"
    assert row["progress"] == 42


def test_job_store_metadata_conversion(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    import src.web.job_store as store
    store = importlib.reload(store)
    store.init()

    class Job:
        id = "done1"
        kind = "ai_cleanup"
        audio_path = "/data/hasil/01_demo"
        config = {}
        status = "pending"

    store.create(Job())
    store.update(Job(), status="done", metadata_json={"md_path": "x.md"})
    row = store.as_dict(store.get("done1"))
    assert row["config"] == {}
    assert row["metadata"] == {"md_path": "x.md"}
