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


def test_waiting_list_is_cleaned_when_job_creation_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    import src.web.job_store as store
    store = importlib.reload(store)
    store.init()
    import src.web.job_manager as manager
    manager = importlib.reload(manager)
    jobs = manager.JobManager()

    def boom(job):
        raise RuntimeError("db locked")

    monkeypatch.setattr(manager.job_store, "create", boom)
    try:
        jobs.create("/data/uploads/a.mp3", {"model": "small"})
    except RuntimeError:
        pass
    assert jobs.queue_status()["waiting"] == 0 and jobs.queue_status()["running"] == 0


def test_ai_jobs_use_separate_slot_from_transcription(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    import src.web.job_store as store
    store = importlib.reload(store)
    store.init()
    import src.web.job_manager as manager
    manager = importlib.reload(manager)
    jobs = manager.JobManager()

    assert jobs._ai_slot.acquire(blocking=False)
    try:
        status = jobs.queue_status()
        assert status["running"] == 0 and status["waiting"] == 0   # job AI tidak memakai slot transkripsi
    finally:
        jobs._ai_slot.release()


def _fresh_manager(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    import src.web.job_store as store
    importlib.reload(store).init()
    import src.web.job_manager as manager
    return importlib.reload(manager)


def test_job_ends_stream_and_frees_slot_even_if_sqlite_fails(tmp_path, monkeypatch):
    manager = _fresh_manager(tmp_path, monkeypatch)
    jobs = manager.JobManager()
    monkeypatch.setattr(manager.TranscribeEngine, "transcribe",
                        classmethod(lambda cls, *a, **k: None))

    def boom(job, **fields):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(manager.job_store, "update", boom)
    job = manager.TranscribeJob("sq1", str(tmp_path / "a.mp3"), {})
    jobs._register(job)
    jobs._run_transcribe_with_slot(job)

    assert job.status == "done"
    assert job.events._items[-1]["type"] == "job_end"
    assert jobs.queue_status() == {**jobs.queue_status(), "running": 0, "waiting": 0}


def test_upload_removed_after_job_ends_but_only_inside_upload_dir(tmp_path, monkeypatch):
    manager = _fresh_manager(tmp_path, monkeypatch)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(manager, "UPLOAD_DIR", upload_dir)
    inside = upload_dir / "a.mp3"
    inside.write_bytes(b"x")
    outside = tmp_path / "keep.mp3"
    outside.write_bytes(b"x")
    monkeypatch.setattr(manager.TranscribeEngine, "transcribe",
                        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(RuntimeError("gagal"))))
    jobs = manager.JobManager()

    for path in (inside, outside):
        job = manager.TranscribeJob(path.stem, str(path), {})
        jobs._register(job)
        jobs._run_transcribe(job)
        assert job.status == "error"

    assert not inside.exists()
    assert outside.exists()


def test_progress_is_saved_only_when_percent_changes(tmp_path, monkeypatch):
    manager = _fresh_manager(tmp_path, monkeypatch)
    jobs = manager.JobManager()
    writes = []
    real_update = manager.job_store.update
    monkeypatch.setattr(manager.job_store, "update",
                        lambda job, **f: (writes.append(f), real_update(job, **f))[1])

    def fake(cls, path, config, callbacks):
        for _ in range(500):
            callbacks["on_progress"](10, "Segmen 1s")
        callbacks["on_progress"](11, "Segmen 2s")

    monkeypatch.setattr(manager.TranscribeEngine, "transcribe", classmethod(fake))
    job = manager.TranscribeJob("pr1", str(tmp_path / "a.mp3"), {})
    jobs._register(job)
    manager.job_store.create(job)
    jobs._run_transcribe(job)

    assert len([w for w in writes if "progress" in w and w.get("status") is None]) == 2


def test_failed_job_with_checkpoint_keeps_upload_and_marks_resumable(tmp_path, monkeypatch):
    manager = _fresh_manager(tmp_path, monkeypatch)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(manager, "UPLOAD_DIR", upload_dir)
    audio = upload_dir / "a.mp3"
    audio.write_bytes(b"x")
    hasil = tmp_path / "hasil" / "01_a"
    hasil.mkdir(parents=True)
    (hasil / "transkrip_sebagian.json").write_text("{}")

    def gagal(cls, *a, **k):
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(manager.TranscribeEngine, "transcribe", classmethod(gagal))
    jobs = manager.JobManager()
    job = manager.TranscribeJob("rs1", str(audio), {"output_dir": str(hasil)})
    jobs._register(job)
    jobs._run_transcribe(job)

    assert job.status == "error" and audio.exists()
    error_event = next(e for e in job.events._items if e["type"] == "error")
    assert error_event["resumable"] is True

    (hasil / "transkrip_sebagian.json").unlink()
    job2 = manager.TranscribeJob("rs2", str(audio), {"output_dir": str(hasil)})
    jobs._register(job2)
    jobs._run_transcribe(job2)
    assert not audio.exists()   # tanpa titik simpan, unggahan dibuang seperti biasa
