"""FastAPI server — dashboard transcribe via browser (IP local).

Run:
    .venv\\Scripts\\python.exe -m src.web.server            # dev, 127.0.0.1
    .venv\\Scripts\\python.exe -m src.web.server --host 0.0.0.0 --port 8765
"""

import argparse
import json
import os
import re
import socket
import threading
import time
import webbrowser
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.core.engine import TranscribeEngine
from src.notulen.ai_generator import ai_config
from src.utils.config import load_config, save_config
from src.utils.ffmpeg_checker import check_ffmpeg
from src.utils.paths import HASIL_DIR, list_history
from src.web.job_manager import JobManager

WEB_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
from src.utils.paths import UPLOAD_DIR  # noqa: E402  (menghormati DATA_DIR)

# Patch WDAC paling awal (R-02 kajian) — sebelum import faster_whisper
TranscribeEngine.apply_wdac_patch()

app = FastAPI(title="Mesin Transcribe GUI", version="0.1.0")
jobs = JobManager()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

ALLOWED_EXT = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}
ALLOWED_MODELS = {"tiny", "base", "small", "medium"}
ALLOWED_LANGUAGES = {"id", "en"}
AI_ENABLED = os.environ.get("AI_ENABLED", "false").strip().lower() == "true"


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name, str(default)).strip()
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


MAX_UPLOAD_BYTES = _env_int("MAX_UPLOAD_BYTES", 2 * 1024**3)


def _within_directory(path: str, directory: Path) -> bool:
    try:
        return Path(path).resolve().is_relative_to(directory.resolve())
    except OSError:
        return False


def _validate_upload_path(path: str) -> str:
    resolved = str(Path(path).resolve())
    if not _within_directory(resolved, UPLOAD_DIR):
        raise HTTPException(400, "File audio harus berasal dari folder upload")
    if not os.path.isfile(resolved):
        raise HTTPException(404, f"File audio tidak ditemukan: {resolved}")
    return resolved


def _sanitize_filename(name: str) -> str:
    name = os.path.basename(name.replace("\\", "/"))
    name = re.sub(r"[^\w.\- ]", "_", name)
    return name.strip() or "audio"


# ── Halaman utama ────────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse(TEMPLATE_DIR / "index.html")


# ── Env check (R-09) ─────────────────────────────────────────────────────
@app.get("/api/env")
def env():
    ff = check_ffmpeg()
    model_cached = TranscribeEngine.is_model_cached("medium")
    return {
        "ffmpeg": ff,
        "model_cached": model_cached,
        "model_default": "medium",
        "output_dir": str(HASIL_DIR),
        "ai": ai_config(),
        "ai_enabled": AI_ENABLED,
        "settings": load_config(),  # settings terakhir tersimpan (persistence)
    }


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ── Upload audio ─────────────────────────────────────────────────────────
@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            400,
            f"Ekstensi {ext or '(kosong)'} tidak didukung. "
            f"Izinkan: {', '.join(sorted(ALLOWED_EXT))}",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(file.filename or "audio")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    stem_ = Path(safe_name).stem
    suffix = Path(safe_name).suffix
    for index in range(1, 1_000_000):
        candidate = safe_name if index == 1 else f"{stem_}-{index}{suffix}"
        dest = UPLOAD_DIR / candidate
        try:
            fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o600)
            break
        except FileExistsError:
            continue
    else:
        raise HTTPException(409, "Tidak dapat menyediakan nama file upload")

    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Ukuran file melebihi batas upload")
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise

    return {"path": str(dest), "filename": dest.name, "size": size}


# ── Transcribe ───────────────────────────────────────────────────────────
@app.post("/api/transcribe")
def start_transcribe(body: dict):
    audio_path = body.get("audio_path") or body.get("file_path")
    if not audio_path:
        raise HTTPException(400, "audio_path wajib diisi")

    model = body.get("model", "medium")
    language = body.get("language", "id")
    if model not in ALLOWED_MODELS:
        raise HTTPException(400, f"Model tidak valid. Pilih: {', '.join(sorted(ALLOWED_MODELS))}")
    if language not in ALLOWED_LANGUAGES:
        raise HTTPException(400, "Bahasa tidak valid. Pilih: id atau en")

    audio_path = _validate_upload_path(audio_path)
    config = {
        "model": model,
        "language": language,
        "device": "cpu",
        "compute_type": "int8",
        "with_md": False,
    }

    try:
        save_config({"model": model, "language": language,
                     "device": config["device"], "compute_type": config["compute_type"]})
    except OSError:
        pass  # gagal simpan bukan error fatal

    job = jobs.create(audio_path, config)
    return job.to_dict()



@app.get("/api/jobs/active")
def active_jobs():
    """Daftar job yang masih aktif untuk recovery setelah browser refresh."""
    return {"items": jobs.active()}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/stream")
def job_stream(job_id: str):
    if not jobs.get(job_id):
        raise HTTPException(404, "Job tidak ditemukan")
    return StreamingResponse(
        jobs.event_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    ok = jobs.cancel(job_id)
    if not ok:
        raise HTTPException(404, "Job tidak ditemukan")
    return {"ok": True}


# ── Notulen AI (Phase 2) ────────────────────────────────────────────────
@app.post("/api/notulen/ai")
def notulen_ai(body: dict):
    """Buat notulen AI dari transkrip di folder hasil → DOCX."""
    if not AI_ENABLED:
        raise HTTPException(
            503,
            "Fitur AI notulen dimatikan di server ini (AI_ENABLED=false)",
        )
    output_dir = body.get("output_dir") or body.get("folder")
    if not output_dir:
        raise HTTPException(400, "output_dir wajib diisi")

    # Pertahankan path absolut caller untuk kompatibilitas macOS; gunakan
    # resolved hanya untuk pemeriksaan containment terhadap symlink.
    fpath = Path(os.path.abspath(os.path.normpath(output_dir)))
    resolved = fpath.resolve()
    if not re.match(r"^\d{2}_[\w\- ]+$", fpath.name):
        raise HTTPException(400, "Nama folder hasil tidak valid (harus XX_nama)")
    if not fpath.is_dir():
        raise HTTPException(404, "Folder hasil tidak ditemukan")
    if not resolved.is_relative_to(HASIL_DIR.resolve()):
        raise HTTPException(400, "Folder di luar direktori hasil tidak diizinkan")

    job = jobs.create_ai(str(fpath))
    return job.to_dict()


@app.post("/api/transcript/cleanup")
def transcript_cleanup(body: dict):
    """Rapikan transkrip dengan AI tanpa mengubah file transkrip asli."""
    if not AI_ENABLED:
        raise HTTPException(
            503,
            "Fitur AI dimatikan di server ini (AI_ENABLED=false)",
        )
    output_dir = body.get("output_dir") or body.get("folder")
    if not output_dir:
        raise HTTPException(400, "output_dir wajib diisi")
    fpath = Path(os.path.abspath(os.path.normpath(output_dir)))
    resolved = fpath.resolve()
    if not re.match(r"^\d{2}_[\w\- ]+$", fpath.name):
        raise HTTPException(400, "Nama folder hasil tidak valid (harus XX_nama)")
    if not fpath.is_dir():
        raise HTTPException(404, "Folder hasil tidak ditemukan")
    if not resolved.is_relative_to(HASIL_DIR.resolve()):
        raise HTTPException(400, "Folder di luar direktori hasil tidak diizinkan")
    return jobs.create_cleanup(str(fpath)).to_dict()


# ── History (hasil transkripsi) ──────────────────────────────────────────
@app.get("/api/history")
def history():
    items = []
    for folder in list_history():
        folder_path = Path(folder)
        resolved_folder = folder_path.resolve()
        if not resolved_folder.is_relative_to(HASIL_DIR.resolve()):
            continue
        files = [f.name for f in resolved_folder.iterdir()
                 if f.is_file() and (
                     not f.name.lower().endswith(".md")
                     or f.name in {"notulen_ai.md", "transkrip_rapi_ai.md"}
                 )]
        files.sort(key=lambda n: (n.startswith("transkrip"), n))
        items.append({"name": resolved_folder.name, "path": str(resolved_folder),
                      "files": files})
    return {"items": items}

@app.delete("/api/history/{folder_name}")
def delete_history(folder_name: str):
    """Hapus satu folder hasil yang dipilih dari history."""
    if not re.match(r"^\d{2}_[\w\- ]+$", folder_name):
        raise HTTPException(400, "Nama folder tidak valid")
    folder = (HASIL_DIR / folder_name).resolve()
    if not folder.is_relative_to(HASIL_DIR.resolve()):
        raise HTTPException(400, "Folder di luar direktori hasil tidak diizinkan")
    if not folder.is_dir():
        raise HTTPException(404, "Folder hasil tidak ditemukan")
    import shutil
    shutil.rmtree(folder)
    return {"ok": True, "deleted": folder_name}


@app.get("/api/history/{folder_name}/file/{file_name}")
def history_file(folder_name: str, file_name: str, download: bool = False):
    if not re.match(r"^\d{2}_[\w\- ]+$", folder_name):
        raise HTTPException(400, "Nama folder tidak valid")
    file_name = os.path.basename(file_name)
    fpath = (HASIL_DIR / folder_name / file_name).resolve()
    if not fpath.is_relative_to(HASIL_DIR.resolve()) or not fpath.is_file():
        raise HTTPException(404, "File tidak ditemukan")

    if download:
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if fpath.suffix.lower() == ".docx"
            else "application/pdf" if fpath.suffix.lower() == ".pdf"
            else "text/plain; charset=utf-8"
        )
        return FileResponse(fpath, filename=fpath.name, media_type=media_type)

    try:
        content = fpath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = fpath.read_text(encoding="utf-8", errors="replace")
    return {"name": file_name, "content": content, "size": fpath.stat().st_size}


# ── Launch helper ────────────────────────────────────────────────────────
def get_local_ips() -> list:
    ips = ["127.0.0.1"]
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return list(dict.fromkeys(ips))


def run_server(host="127.0.0.1", port=8765, open_browser=True):
    import uvicorn

    if host in ("0.0.0.0", "::"):
        urls = [f"http://{ip}:{port}" for ip in get_local_ips()]
    else:
        urls = [f"http://{host}:{port}"]

    print("=" * 56)
    print("  MESIN TRANSCRIBE — DASHBOARD")
    print("=" * 56)
    for u in urls:
        print(f"  Buka di browser: {u}")
    print("  Tekan Ctrl+C untuk menghentikan server.")
    print("=" * 56)

    if open_browser:
        def _open():
            time.sleep(1.2)
            webbrowser.open(urls[0])
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dashboard Mesin Transcribe")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind host (default 127.0.0.1; 0.0.0.0 = semua)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true",
                        help="Jangan buka browser otomatis")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)
