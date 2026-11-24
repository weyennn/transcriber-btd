"""Perbaikan hasil audit: healthz, nama berkas panjang, potongan audio, dekoder."""

import importlib
import io

import numpy as np
import pytest


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "config"))
    import src.utils.paths as paths
    importlib.reload(paths)
    import src.web.server as srv
    return importlib.reload(srv)


def test_healthz_reports_missing_ffmpeg_with_503(server, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "check_ffmpeg", lambda: {"ok": False})
    server._health_cache["at"] = 0
    response = TestClient(server.app).get("/healthz")
    assert response.status_code == 503
    assert response.json()["ok"] is False
    assert "ffmpeg tidak tersedia" in response.json()["problems"]


def test_healthz_reports_missing_gpu_when_cuda_requested(server, monkeypatch):
    from fastapi.testclient import TestClient
    import types, sys
    monkeypatch.setattr(server, "check_ffmpeg", lambda: {"ok": True})
    monkeypatch.setitem(server.TRANSCRIPTION_RUNTIME, "device", "cuda")
    monkeypatch.setitem(sys.modules, "ctranslate2",
                        types.SimpleNamespace(get_cuda_device_count=lambda: 0))
    server._health_cache["at"] = 0
    response = TestClient(server.app).get("/healthz")
    assert response.status_code == 503
    assert "GPU CUDA tidak terdeteksi" in response.json()["problems"]


def test_healthz_ok_when_environment_is_healthy(server, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "check_ffmpeg", lambda: {"ok": True})
    monkeypatch.setitem(server.TRANSCRIPTION_RUNTIME, "device", "cpu")
    server._health_cache["at"] = 0
    response = TestClient(server.app).get("/healthz")
    assert response.status_code == 200 and response.json() == {"ok": True}


def test_long_filename_is_shortened_but_keeps_extension(server):
    name = "rapat_" + "a" * 300 + ".mp3"
    safe = server._sanitize_filename(name)
    assert len(safe) <= 116 and safe.endswith(".mp3")
    assert server._sanitize_filename("rapat.mp3") == "rapat.mp3"


def test_chunk_seconds_from_env_rejects_bad_values(monkeypatch):
    from src.core.engine import _chunk_seconds_from_env
    for bad in ("-5", "0", "abc", "10"):
        monkeypatch.setenv("TRANSCRIBE_CHUNK_SECONDS", bad)
        assert _chunk_seconds_from_env() == 600.0
    monkeypatch.setenv("TRANSCRIBE_CHUNK_SECONDS", "120")
    assert _chunk_seconds_from_env() == 120.0


def test_iter_audio_chunks_terminates_with_nonpositive_chunk_seconds(tmp_path):
    import shutil, subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg tidak ada")
    wav = tmp_path / "s.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=2",
                    "-ar", "16000", str(wav)], check=True)
    from src.core.audio_decoder import iter_audio_chunks
    chunks = list(iter_audio_chunks(str(wav), chunk_seconds=-1))
    assert sum(len(c) for _, c in chunks) > 0


def test_decode_audio_cleans_temp_file_and_reports_ffmpeg_error(tmp_path, monkeypatch):
    import glob, tempfile
    from src.core import audio_decoder
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with pytest.raises(RuntimeError, match="ffmpeg decode failed"):
        audio_decoder.decode_audio(io.BytesIO(b"bukan audio"))
    assert glob.glob(str(tmp_path / "*.tmp")) == []


def _failed_job(server, tmp_path, job_id, with_checkpoint=True, status="error"):
    from src.web import job_store
    from src.utils.paths import upload_dir_for, result_dir_for
    job_store.init()
    uploads, results = upload_dir_for("legacy"), result_dir_for("legacy")
    uploads.mkdir(parents=True, exist_ok=True)
    audio = uploads / "a.mp3"
    audio.write_bytes(b"x")
    out = results / "01_a"
    out.mkdir(parents=True, exist_ok=True)
    if with_checkpoint:
        (out / "transkrip_sebagian.json").write_text("{}")

    class J:
        id, kind, audio_path = job_id, "transcribe", str(audio)
        config = {"model": "small", "language": "id", "output_dir": str(out)}
        status = "pending"
    job_store.create(J())
    job_store.update(J(), status=status)
    return audio, out


def test_resume_endpoint_starts_job_with_resume_flag(server, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    _failed_job(server, tmp_path, "rs-ok")
    seen = {}

    class FakeJob:
        def to_dict(self):
            return {"id": "new1", "kind": "transcribe"}

    def fake_create(audio_path, config, owner_id="legacy"):
        seen.update(config)
        return FakeJob()

    monkeypatch.setattr(server.jobs, "create", fake_create)
    response = TestClient(server.app).post("/api/jobs/rs-ok/resume")
    assert response.status_code == 200 and response.json()["id"] == "new1"
    assert seen["resume"] is True and seen["model"] == "small"


def test_resume_endpoint_rejects_missing_checkpoint_busy_worker_and_wrong_status(server, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    client = TestClient(server.app)
    assert client.post("/api/jobs/tidak-ada/resume").status_code == 404
    audio, out = _failed_job(server, tmp_path, "rs-bad", status="done")
    assert client.post("/api/jobs/rs-bad/resume").status_code == 409      # status bukan gagal
    from src.web import job_store
    job_store._connect().execute("UPDATE jobs SET status='error' WHERE id='rs-bad'").connection.commit()
    monkeypatch.setattr(server.jobs, "create", lambda *a, **k: None)
    assert client.post("/api/jobs/rs-bad/resume").status_code == 409      # worker sibuk
    (out / "transkrip_sebagian.json").unlink()
    assert client.post("/api/jobs/rs-bad/resume").status_code == 410      # titik simpan hilang


def test_stale_uploads_are_purged_but_recent_and_tmp_kept(server, tmp_path):
    import os, time
    from src.utils.paths import UPLOAD_DIR
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / ".tmp").mkdir(exist_ok=True)
    old, new, tmpf = UPLOAD_DIR / "old.mp3", UPLOAD_DIR / "new.mp3", UPLOAD_DIR / ".tmp" / "x"
    for f in (old, new, tmpf):
        f.write_bytes(b"x")
    past = time.time() - 9 * 86400
    os.utime(old, (past, past)); os.utime(tmpf, (past, past))
    assert server._purge_stale_uploads() == 1
    assert not old.exists() and new.exists() and tmpf.exists()


def test_client_has_resume_button_wired_to_resume_endpoint():
    from pathlib import Path
    root = Path(__file__).parents[1] / "src" / "web"
    js = (root / "static" / "app.js").read_text(encoding="utf-8")
    html = (root / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'id="btn-resume"' in html
    assert "api/jobs/${failedJobId}/resume" in js
    assert "data.resumable" in js


def test_language_auto_is_accepted_by_server_and_offered_in_ui(server):
    from pathlib import Path
    assert "auto" in server.ALLOWED_LANGUAGES
    html = (Path(__file__).parents[1] / "src" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    assert '<option value="auto" selected>' in html  # deteksi otomatis jadi bawaan
