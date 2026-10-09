"""Test API dashboard web (FastAPI TestClient) — regresi end-to-end.

Menjalankan transcribe asli pada sample_75s.mp3 (model small, sudah di
cache) — sekitar 12-20 detik. Stream SSE diverifikasi event-by-event.
"""

import json
import time

import os
import importlib
import tempfile
import pytest

os.environ["AUTH_ENABLED"] = "false"
os.environ["AI_ENABLED"] = "true"

from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def fresh_server_client():
    global client
    os.environ["AUTH_ENABLED"] = "false"
    import src.web.auth as auth
    importlib.reload(auth)
    import src.utils.paths as paths
    importlib.reload(paths)

    importlib.reload(paths)
    import src.core.engine as engine
    importlib.reload(engine)
    engine.TranscribeEngine.apply_wdac_patch()
    import src.web.server as server
    importlib.reload(server)
    client = TestClient(server.app)
    yield
    os.environ["AI_ENABLED"] = "true"

SAMPLE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sample_audio", "sample_75s.mp3",
)


def test_index_page():
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="portal-enter"' in r.text
    assert "Pilih rekaman</a>" not in r.text
    assert 'rel="icon" type="image/svg+xml" href="static/assets/pandora-favicon.svg' in r.text
    assert "Untuk masuk, gunakan akun Google UGM." in r.text
    assert 'id="portal-google-login"' not in r.text
    assert "Google terverifikasi akun UGM" not in r.text
    assert 'class="portal-flow-scene"' in r.text
    assert "flow-audio-disc" in r.text
    assert "flow-transcript" in r.text
    assert "Transcriber Audio" in r.text
    assert 'aria-label="Transkrip JSON mentah"' in r.text
    assert '>Rapi AI</button>' in r.text
    assert 'aria-label="Notulensi rapat AI"' in r.text
    assert '>Notulensi</button>' in r.text
    assert 'id="btn-download-cleaned-md"' in r.text
    assert 'id="btn-download-minutes-md"' in r.text


def test_authenticated_user_status_is_a_greeting():
    from pathlib import Path
    app_js = Path(__file__).parents[1] / "src" / "web" / "static" / "app.js"
    source = app_js.read_text(encoding="utf-8")
    assert '`Halo, ${user.name || user.email || "pengguna"}!`' in source


def test_client_accepts_extended_audio_and_video_formats():
    from pathlib import Path
    source = (Path(__file__).parents[1] / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    for ext in (".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".wma", ".opus"):
        assert f'"{ext}"' in source


def test_client_ignores_missing_or_zero_upload_limit():
    """A zero/blank limit must not disable every non-empty selected file."""
    from pathlib import Path
    source = (Path(__file__).parents[1] / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "Number(env.max_upload_bytes) > 0" in source


def test_upload_picker_uses_a_native_label_and_change_handler():
    """Choosing a file must not depend solely on a scripted hidden-input click."""
    from pathlib import Path
    root = Path(__file__).parents[1]
    template = (root / "src" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    source = (root / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'for="file-input"' in template
    assert 'class="file-input"' in template
    assert 'fileInput.addEventListener("change", handleSelectedInputFile)' in source
    assert 'id="btn-remove-file"' in template
    assert 'btnRemoveFile.addEventListener("click", clearSelectedFile)' in source
    assert "fileInput.value = \"\"" in source
    css = (root / "src" / "web" / "static" / "style.css").read_text(encoding="utf-8")
    assert ".dropzone { position: relative;" in css
    assert ".file-picker { position: absolute; inset: 0;" in css


def test_client_has_durable_job_status_fallback_and_sse_reconnect():
    from pathlib import Path
    source = (Path(__file__).parents[1] / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "startJobStatusPolling(job.id)" in source
    assert "api/jobs/${encodeURIComponent(jobId)}" in source
    assert "setInterval(() => pollJobStatus(jobId), 5000)" in source
    assert "Koneksi progress tersambung ulang..." in source
    assert "stopJobStatusPolling();" in source


def test_transcription_progress_uses_backend_percentage_without_offset():
    from pathlib import Path
    source = (Path(__file__).parents[1] / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "setProgress(data.percent, data.message)" in source
    assert "const percent = rawProgress;" in source
    assert "20 + Math.round" not in source


def test_transcription_progress_reports_loading_and_saving_phases():
    from pathlib import Path
    engine = (Path(__file__).parents[1] / "src" / "core" / "engine.py").read_text(encoding="utf-8")
    assert 'progress(0, "Memuat model transkripsi...")' in engine
    assert 'progress(99, "Menyimpan hasil transkripsi...")' in engine


def test_ai_actions_show_estimated_progress_during_llm_call():
    from pathlib import Path
    source = (Path(__file__).parents[1] / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert '"AI sedang bekerja · persentase perkiraan"' in source
    assert "aiProgressValue < 78" in source
    assert "stopAiProgressEstimate();" in source
    assert "/Memanggil AI/i.test(data.message || \"\")" in source


def test_client_locks_other_actions_while_job_runs():
    from pathlib import Path
    source = (Path(__file__).parents[1] / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "setActionControlsLocked(true)" in source
    assert "setActionControlsLocked(false)" in source
    assert "running) return;" in source
    assert "aria-disabled" in source


def test_client_shows_global_transcription_queue_status():
    from pathlib import Path
    source = (Path(__file__).parents[1] / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "api/jobs/queue-status" in source
    assert "Worker sedang digunakan" in source
    assert "Masuk antrean" in source


def test_queue_status_endpoint_uses_aggregate_counts():
    from pathlib import Path
    source = (Path(__file__).parents[1] / "src" / "web" / "server.py").read_text(encoding="utf-8")
    assert '@app.get("/api/jobs/queue-status")' in source
    store = (Path(__file__).parents[1] / "src" / "web" / "job_store.py").read_text(encoding="utf-8")
    assert "running_count" in store
    assert "pending_count" in store


def test_job_status_includes_private_queue_position():
    from pathlib import Path
    root = Path(__file__).parents[1]
    server = (root / "src" / "web" / "server.py").read_text(encoding="utf-8")
    store = (root / "src" / "web" / "job_store.py").read_text(encoding="utf-8")
    client = (root / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "queue_position" in store
    assert "queue_ahead" in server
    assert "Masuk antrean" in client
    assert "pekerjaan di depan Anda" in client


def test_returning_authenticated_session_auto_opens_workspace():
    from pathlib import Path
    app_js = Path(__file__).parents[1] / "src" / "web" / "static" / "app.js"
    source = app_js.read_text(encoding="utf-8")
    # Setiap sesi yang sudah login (termasuk baru kembali dari Google) langsung
    # membuka workspace tanpa menampilkan halaman depan portal.
    assert 'if (authenticated && authEnabled && portalIntro && appShell)' in source
    assert 'params.get("auth") === "success"' in source
    assert 'params.get("auth") !== "success"' not in source



def test_env():
    r = client.get("/api/env")
    assert r.status_code == 200
    d = r.json()
    assert d["ffmpeg"]["ok"] is True
    assert isinstance(d["model_cached"], bool)
    assert d["model_default"] == "medium"


def test_upload_and_transcribe_sse():
    if not os.path.exists(SAMPLE):
        import pytest
        pytest.skip("sample_audio/sample_75s.mp3 tidak ada")

    with open(SAMPLE, "rb") as f:
        up = client.post("/api/upload", files={"file": ("sample_75s.mp3", f, "audio/mpeg")})
    assert up.status_code == 200, up.text
    path = up.json()["path"]

    job = client.post("/api/transcribe", json={
        "audio_path": path, "language": "id",
    })
    assert job.status_code == 200, job.text
    job_id = job.json()["id"]

    events = []
    with client.stream("GET", f"/api/jobs/{job_id}/stream") as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("event:") and not line.startswith("event: :"):
                events.append(line.split("event: ", 1)[1].strip())

    kinds = [e for e in events if e != "heartbeat"]
    assert "log" in kinds
    assert "progress" in kinds
    assert "segment" in kinds
    assert "finished" in kinds
    assert "job_end" in kinds
    assert "error" not in kinds

    # Output folder terdaftar di history
    hist = client.get("/api/history").json()["items"]
    assert len(hist) >= 1


def test_upload_invalid_ext():
    r = client.post("/api/upload", files={"file": ("tes.txt", b"hello", "text/plain")})
    assert r.status_code == 400


@pytest.mark.parametrize("filename", [
    "recording.wma", "recording.aiff", "recording.amr", "recording.opus",
    "recording.webm", "recording.mp4", "recording.m4v", "recording.mov",
    "recording.mkv", "recording.avi",
])
def test_upload_accepts_common_ffmpeg_audio_containers(filename):
    response = client.post("/api/upload", files={"file": (filename, b"fixture", "application/octet-stream")})
    assert response.status_code == 200, response.text
    uploaded = response.json()["path"]
    try:
        assert os.path.isfile(uploaded)
    finally:
        os.unlink(uploaded)


def test_job_not_found():
    r = client.get("/api/jobs/tidak-ada")
    assert r.status_code == 404


# ── Notulen AI (Phase 2) ────────────────────────────────────────────────

def _make_test_folder(name="99_ai-test"):
    """Buat folder hasil sementara di HASIL_DIR (dibersihkan setelah test)."""
    from src.web.server import HASIL_DIR
    folder = HASIL_DIR / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "transkrip.txt").write_text(
        "Rapat membahas peluncuran sistem OJS. Keputusan: lanjut bulan depan.",
        encoding="utf-8",
    )
    return folder


def test_history_hides_md_files():
    folder = _make_test_folder()
    (folder / "Notulen_rapat.md").write_text("# lama", encoding="utf-8")
    (folder / "notulen_ai.md").write_text("# ai", encoding="utf-8")
    (folder / "transkrip_rapi_ai.md").write_text("# rapi", encoding="utf-8")
    try:
        items = client.get("/api/history").json()["items"]
        target = next(i for i in items if i["name"] == folder.name)
        assert "Notulen_rapat.md" not in target["files"]
        assert "notulen_ai.md" in target["files"]
        assert "transkrip_rapi_ai.md" in target["files"]
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def test_notulen_ai_endpoint(monkeypatch):
    import src.notulen.ai_generator as ag

    calls = {}

    def fake_generate(output_dir, callbacks):
        calls["output_dir"] = output_dir
        cb = callbacks or {}
        if cb.get("on_log"):
            cb["on_log"]("fake AI berjalan")
        result = {
            "docx_path": os.path.join(output_dir, "NotulenAI_ai-test.docx"),
            "txt_path": os.path.join(output_dir, "notulen_ai.txt"),
            "model": "mock",
            "chars_in": 50,
            "duration_s": 0.1,
        }
        if cb.get("on_finished"):
            cb["on_finished"](result)
        return result

    monkeypatch.setattr(ag, "generate_notulen_docx", fake_generate)

    folder = _make_test_folder()
    try:
        job = client.post("/api/notulen/ai", json={"output_dir": str(folder)})
        assert job.status_code == 200, job.text
        job_id = job.json()["id"]
        assert job.json()["kind"] == "ai_notulen"

        kinds = []
        with client.stream("GET", f"/api/jobs/{job_id}/stream") as r:
            assert r.status_code == 200
            for line in r.iter_lines():
                if line.startswith("event:") and not line.startswith("event: :"):
                    kinds.append(line.split("event: ", 1)[1].strip())

        kinds = [k for k in kinds if k != "heartbeat"]
        assert "finished" in kinds
        assert "job_end" in kinds
        assert "error" not in kinds
        assert calls.get("output_dir") == str(folder)
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def test_cleanup_endpoint(monkeypatch):
    import src.notulen.ai_generator as ag

    calls = {}

    def fake_cleanup(output_dir, callbacks):
        calls["output_dir"] = output_dir
        result = {
            "txt_path": os.path.join(output_dir, "transkrip_rapi_ai.txt"),
            "model": "mock", "context": "rapat atau diskusi",
            "chars_in": 50, "duration_s": 0.1,
        }
        if callbacks.get("on_finished"):
            callbacks["on_finished"](result)
        return result

    monkeypatch.setattr(ag, "generate_cleanup", fake_cleanup)
    folder = _make_test_folder()
    try:
        job = client.post("/api/transcript/cleanup", json={"output_dir": str(folder)})
        assert job.status_code == 200, job.text
        assert job.json()["kind"] == "ai_cleanup"
        job_id = job.json()["id"]
        for _ in range(100):
            if calls.get("output_dir"):
                break
            time.sleep(0.01)
        assert calls.get("output_dir") == str(folder)
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def test_notulen_ai_rejects_outside_folder():
    r = client.post("/api/notulen/ai", json={"output_dir": os.getcwd()})
    assert r.status_code == 400  # bukan pola XX_nama


def test_download_docx():
    folder = _make_test_folder()
    (folder / "NotulenAI_ai-test.docx").write_bytes(b"PK fake docx")
    try:
        r = client.get(
            f"/api/history/{folder.name}/file/NotulenAI_ai-test.docx?download=1"
        )
        assert r.status_code == 200
        assert r.content == b"PK fake docx"
        assert "attachment" in r.headers.get("content-disposition", "")
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def test_download_original_transcript():
    folder = _make_test_folder()
    (folder / "transkrip.txt").write_text(
        "Ini transkrip asli yang sudah dirapikan.", encoding="utf-8"
    )
    try:
        response = client.get(
            f"/api/history/{folder.name}/file/Transkrip_{folder.name}.docx?download=1"
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert "attachment" in response.headers.get("content-disposition", "")
        import io
        from docx import Document
        document = Document(io.BytesIO(response.content))
        assert "Ini transkrip asli yang sudah dirapikan." in "\n".join(
            paragraph.text for paragraph in document.paragraphs
        )
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def test_download_original_transcript_generates_docx_for_sanitized_dotted_folder_name():
    folder = _make_test_folder("01_Gang Mulia V No. 84 2")
    try:
        response = client.get(
            "/api/history/01_Gang%20Mulia%20V%20No.%2084%202/"
            "file/Transkrip_01_Gang%20Mulia%20V%20No%2084%202.docx?download=1"
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def test_download_formatted_transcript_docx():
    from docx import Document

    folder = _make_test_folder()
    source_text = "Ini transkrip asli tanpa struktur notulen AI."
    (folder / "transkrip.txt").write_text(source_text, encoding="utf-8")
    (folder / "transkrip.json").write_text(
        json.dumps({"segments": [{"text": source_text}]}), encoding="utf-8"
    )
    try:
        response = client.get(
            f"/api/history/{folder.name}/file/Transkrip_{folder.name}.docx?download=1"
        )
        assert response.status_code == 200
        assert "attachment" in response.headers.get("content-disposition", "")
        import io
        document = Document(io.BytesIO(response.content))
        assert source_text in "\\n".join(p.text for p in document.paragraphs)
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
