"""Antrean transkripsi: dua proses paralel, sisanya menunggu urut kedatangan."""
import importlib
import threading
import time

import pytest


def _manager(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    import src.utils.config as config
    importlib.reload(config)
    import src.web.job_store as store
    importlib.reload(store).init()
    import src.web.job_manager as manager
    return importlib.reload(manager)


class MesinTiruan:
    """Mesin yang menahan setiap job sampai gerbangnya dibuka; mencatat urutan mulai."""

    def __init__(self):
        self.gates = {}
        self.started = []
        self.lock = threading.Lock()

    def transcribe(self, audio_path, config, callbacks):
        with self.lock:
            self.started.append(audio_path)
            gate = self.gates.setdefault(audio_path, threading.Event())
        while not gate.wait(0.02):
            if callbacks["is_cancelled"]():
                raise __import__("src.core.engine", fromlist=["CancelledError"]).CancelledError()

    def open(self, audio_path):
        with self.lock:
            self.gates.setdefault(audio_path, threading.Event()).set()


def _install(manager, monkeypatch):
    mesin = MesinTiruan()
    monkeypatch.setattr(manager.TranscribeEngine, "transcribe",
                        classmethod(lambda cls, p, c, cb: mesin.transcribe(p, c, cb)))
    return mesin


def _until(condition, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_two_jobs_run_together_and_the_rest_wait_in_arrival_order(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch, MAX_CONCURRENT_TRANSCRIBE=2, MAX_TRANSCRIBE_PER_USER=5)
    mesin = _install(manager, monkeypatch)
    jobs = manager.JobManager()

    a = jobs.create("a.mp3", {}, owner_id="u1")
    b = jobs.create("b.mp3", {}, owner_id="u2")
    c = jobs.create("c.mp3", {}, owner_id="u3")
    d = jobs.create("d.mp3", {}, owner_id="u4")

    assert _until(lambda: set(mesin.started) == {"a.mp3", "b.mp3"})
    assert _until(lambda: c.queue_position == 1 and d.queue_position == 2)
    assert c.status == "pending" and d.status == "pending"
    assert jobs.queue_status()["running"] == 2 and jobs.queue_status()["waiting"] == 2
    time.sleep(0.2)
    assert "c.mp3" not in mesin.started            # belum boleh jalan

    mesin.open("a.mp3")                             # satu selesai → c (yang pertama menunggu) jalan
    assert _until(lambda: "c.mp3" in mesin.started)
    assert "d.mp3" not in mesin.started
    assert _until(lambda: d.queue_position == 1)

    mesin.open("b.mp3")
    assert _until(lambda: "d.mp3" in mesin.started)
    assert mesin.started == ["a.mp3", "b.mp3", "c.mp3", "d.mp3"]
    for name in ("c.mp3", "d.mp3"):
        mesin.open(name)
    assert _until(lambda: all(j.status == "done" for j in (a, b, c, d)))
    assert jobs.queue_status()["running"] == 0 and jobs.queue_status()["waiting"] == 0
    messages = [e.get("message", "") for e in c.events._items]
    assert any("urutan 1" in m for m in messages)


def test_single_slot_setting_keeps_jobs_serial(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch, MAX_CONCURRENT_TRANSCRIBE=1, MAX_TRANSCRIBE_PER_USER=5)
    mesin = _install(manager, monkeypatch)
    jobs = manager.JobManager()
    a = jobs.create("a.mp3", {}, owner_id="u1")
    b = jobs.create("b.mp3", {}, owner_id="u2")
    assert _until(lambda: mesin.started == ["a.mp3"])
    time.sleep(0.2)
    assert mesin.started == ["a.mp3"] and b.queue_position == 1
    mesin.open("a.mp3")
    assert _until(lambda: "b.mp3" in mesin.started)
    mesin.open("b.mp3")
    assert _until(lambda: b.status == "done")


def test_cancelling_a_waiting_job_removes_it_without_running(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch, MAX_CONCURRENT_TRANSCRIBE=1, MAX_TRANSCRIBE_PER_USER=5)
    mesin = _install(manager, monkeypatch)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(manager, "UPLOAD_DIR", upload_dir)
    audio = upload_dir / "b.mp3"
    audio.write_bytes(b"x")
    hasil = tmp_path / "hasil" / "02_b"
    hasil.mkdir(parents=True)
    jobs = manager.JobManager()
    jobs.create("a.mp3", {}, owner_id="u1")
    b = jobs.create(str(audio), {"output_dir": str(hasil)}, owner_id="u2")
    c = jobs.create("c.mp3", {}, owner_id="u3")
    assert _until(lambda: b.queue_position == 1 and c.queue_position == 2)

    assert jobs.cancel(b.id, "u2") is True
    # job_end adalah langkah terakhir pembersihan; tunggu sampai ia terkirim sebelum memeriksa sisanya.
    assert _until(lambda: b.events._items and b.events._items[-1]["type"] == "job_end")
    assert b.status == "cancelled"
    assert str(audio) not in mesin.started
    assert not audio.exists() and not hasil.exists()      # unggahan dan folder kosong dibuang
    assert _until(lambda: c.queue_position == 1)           # yang di belakang maju

    mesin.open("a.mp3")
    assert _until(lambda: "c.mp3" in mesin.started)
    mesin.open("c.mp3")
    assert _until(lambda: c.status == "done")


def test_per_user_limit_and_full_queue_are_refused(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch, MAX_CONCURRENT_TRANSCRIBE=1,
                       MAX_TRANSCRIBE_PER_USER=2, MAX_TRANSCRIBE_QUEUE=2)
    mesin = _install(manager, monkeypatch)
    jobs = manager.JobManager()
    jobs.create("a1.mp3", {}, owner_id="u1")
    jobs.create("a2.mp3", {}, owner_id="u1")
    with pytest.raises(manager.QueueFull, match="batas 2"):
        jobs.create("a3.mp3", {}, owner_id="u1")
    jobs.create("b1.mp3", {}, owner_id="u2")        # menunggu: a2, b1 → penuh (2)
    assert _until(lambda: jobs.queue_status()["waiting"] == 2)
    with pytest.raises(manager.QueueFull, match="Antrean penuh"):
        jobs.create("c1.mp3", {}, owner_id="u3")
    for name in ("a1.mp3", "a2.mp3", "b1.mp3"):
        mesin.open(name)
    assert _until(lambda: jobs.queue_status()["running"] == 0 and jobs.queue_status()["waiting"] == 0)


def test_failed_job_frees_its_slot_for_the_next_in_line(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch, MAX_CONCURRENT_TRANSCRIBE=1, MAX_TRANSCRIBE_PER_USER=5)
    seen = []

    def mesin(cls, path, config, callbacks):
        seen.append(path)
        if path == "a.mp3":
            raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(manager.TranscribeEngine, "transcribe", classmethod(mesin))
    jobs = manager.JobManager()
    a = jobs.create("a.mp3", {}, owner_id="u1")
    b = jobs.create("b.mp3", {}, owner_id="u2")
    assert _until(lambda: a.status == "error" and b.status == "done")
    assert seen == ["a.mp3", "b.mp3"]


def test_worker_status_endpoint_reports_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    manager = _manager(tmp_path, monkeypatch, MAX_CONCURRENT_TRANSCRIBE=2)
    import src.web.server as server
    importlib.reload(server)
    from fastapi.testclient import TestClient
    body = TestClient(server.app).get("/api/jobs/worker-status").json()
    assert body == {"running": 0, "waiting": 0, "capacity": 2, "max_waiting": 20,
                    "per_user": 2, "busy": False}


def test_model_is_loaded_once_with_workers_matching_concurrency(monkeypatch):
    import sys
    import types
    monkeypatch.setenv("MAX_CONCURRENT_TRANSCRIBE", "2")
    import src.utils.config as config
    importlib.reload(config)
    from src.core.engine import TranscribeEngine

    dibuat = []

    class WhisperModelTiruan:
        def __init__(self, name, **kwargs):
            time.sleep(0.1)
            dibuat.append((name, kwargs))

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=WhisperModelTiruan))
    monkeypatch.setattr(TranscribeEngine, "apply_wdac_patch", classmethod(lambda cls: None))
    monkeypatch.setattr(TranscribeEngine, "_model_cache", {})

    hasil = []
    threads = [threading.Thread(target=lambda: hasil.append(TranscribeEngine.load_model("small", "cpu", "int8")))
               for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(dibuat) == 1                         # dua job serentak memakai satu model
    assert dibuat[0][1]["num_workers"] == 2
    assert hasil[0] is hasil[1]
