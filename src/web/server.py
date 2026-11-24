"""FastAPI server — dashboard transcribe via browser (IP local).

Run:
    .venv\\Scripts\\python.exe -m src.web.server            # dev, 127.0.0.1
    .venv\\Scripts\\python.exe -m src.web.server --host 0.0.0.0 --port 8765
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import socket
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from src.core.engine import TranscribeEngine
from src.notulen.ai_generator import ai_config, check_ai_router
from src.utils.ai_notice import CATATAN_TRANSKRIP
from src.utils.retention import retention_days
from src.utils.config import load_config, save_config, transcription_runtime
from src.utils.ffmpeg_checker import check_ffmpeg
from src.utils.paths import HASIL_DIR, list_history, result_dir_for, upload_dir_for
from src.web.auth import auth_me, callback as auth_callback, get_current_user, is_archive_admin, login as auth_login, logout as auth_logout, user_id
from src.web.job_manager import JobManager
from src.web import job_store

WEB_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
from src.utils.paths import UPLOAD_DIR  # noqa: E402  (menghormati DATA_DIR)



def _use_disk_backed_temp_dir() -> Path | None:
    """Arahkan berkas sementara ke disk data, bukan /tmp.

    Starlette menampung setiap unggahan di berkas sementara sebelum endpoint
    berjalan. Di container, /tmp adalah tmpfs yang dihitung sebagai memori, jadi
    unggahan 2 GB menghabiskan 2 GB RAM dan container mati kehabisan memori.
    """
    if not os.environ.get("DATA_DIR", "").strip():
        return None  # mode lokal: direktori sementara sistem sudah di disk
    import tempfile
    target = UPLOAD_DIR / ".tmp"
    try:
        target.mkdir(parents=True, exist_ok=True)
        # Sisa unggahan yang terputus saat service berhenti.
        for leftover in target.iterdir():
            if leftover.is_file():
                leftover.unlink(missing_ok=True)
    except OSError:
        return None
    tempfile.tempdir = str(target)
    return target


_use_disk_backed_temp_dir()


STALE_UPLOAD_DAYS = 7


def _purge_stale_uploads(max_age_days: int = STALE_UPLOAD_DAYS) -> int:
    """Hapus unggahan yang tertahan (job gagal yang tak pernah dilanjutkan) setelah beberapa hari."""
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    try:
        for path in UPLOAD_DIR.rglob("*"):
            if path.is_file() and ".tmp" not in path.parts and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
    except OSError:
        pass
    return removed


_purge_stale_uploads()

# Patch WDAC paling awal (R-02 kajian) — sebelum import faster_whisper
TranscribeEngine.apply_wdac_patch()

RETENTION_CHECK_SECONDS = 6 * 3600


def _run_retention_forever():
    from src.utils.retention import purge_expired_results, retention_days
    while True:
        days = retention_days()
        if days > 0:
            try:
                removed = purge_expired_results(days)
                job_store.purge_finished_before(time.time() - days * 86400)
                if removed:
                    print(f"[retensi] {len(removed)} folder hasil dihapus (lebih dari {days} hari).", flush=True)
            except Exception as exc:  # noqa: BLE001 — pembersihan tidak boleh mematikan server
                print(f"[retensi] gagal: {exc}", flush=True)
        time.sleep(RETENTION_CHECK_SECONDS)


@asynccontextmanager
async def _lifespan(_app):
    threading.Thread(target=_run_retention_forever, daemon=True, name="retention").start()
    yield


app = FastAPI(title="Pandora", version="0.1.0", lifespan=_lifespan)
jobs = JobManager()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

ALLOWED_EXT = {
    ".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg",
    ".wma", ".aiff", ".aif", ".amr", ".opus",
    ".webm", ".mp4", ".m4v", ".mov", ".mkv", ".avi",
}
ALLOWED_MODELS = {"tiny", "base", "small", "medium"}
ALLOWED_LANGUAGES = {"id", "en", "auto"}
AI_ENABLED = os.environ.get("AI_ENABLED", "false").strip().lower() == "true"
TRANSCRIPTION_RUNTIME = transcription_runtime()


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


def _owner_id(user: dict) -> str:
    return "legacy" if user.get("dev") else user_id(user)


def _user_upload_dir(user: dict) -> Path:
    return upload_dir_for(_owner_id(user))


def _user_result_dir(user: dict) -> Path:
    return result_dir_for(_owner_id(user))


def _result_folder_for_user(value: str, owner_id: str) -> Path:
    if not re.fullmatch(r"\d{2,}_[\w.\- ]+", value):
        raise HTTPException(400, "Nama folder hasil tidak valid")
    root = result_dir_for(owner_id).resolve()
    folder = (root / value).resolve()
    if not folder.is_relative_to(root):
        raise HTTPException(400, "Folder di luar direktori hasil tidak diizinkan")
    return folder


def _sanitize_filename(name: str) -> str:
    name = os.path.basename(name.replace("\\", "/"))
    name = re.sub(r"[^\w.\- ]", "_", name).strip() or "audio"
    # Nama berkas dan nama folder hasil dibatasi ~255 byte oleh sistem berkas.
    stem_, ext_ = os.path.splitext(name)
    return stem_[:100].rstrip() + ext_[:16] if len(name) > 116 else name

def _resolve_result_folder(value: str) -> Path:
    """Resolve a result folder name or legacy absolute path safely."""
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = HASIL_DIR / candidate.name
    return Path(os.path.abspath(os.path.normpath(str(candidate))))


@app.get("/")
def index():
    return FileResponse(TEMPLATE_DIR / "index.html")


@app.get("/api/auth/me")
def auth_me_route(request: Request):
    return auth_me(request)


@app.get("/api/auth/login")
def auth_login_route(request: Request):
    return auth_login(request)


@app.get("/api/auth/callback")
def auth_callback_route(request: Request):
    return auth_callback(request)


@app.post("/api/auth/logout")
def auth_logout_route():
    return auth_logout()


# ── Env check (R-09) ─────────────────────────────────────────────────────
@app.get("/api/env")
def env(_user: dict = Depends(get_current_user)):
    ff = check_ffmpeg()
    model_cached = TranscribeEngine.is_model_cached("medium")
    ai = ai_config()
    ai["router"] = check_ai_router() if AI_ENABLED else {
        "reachable": False,
        "ok": False,
        "status_code": None,
        "error": "AI_ENABLED=false",
    }
    return {
        "ffmpeg": ff,
        "model_cached": model_cached,
        "model_default": "medium",
        "output_dir": str(_user_result_dir(_user)),
        "ai": ai,
        "ai_enabled": AI_ENABLED,
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_text_bytes": MAX_TEXT_BYTES,
        "retention_days": retention_days(),
        "settings": load_config(_owner_id(_user)),
    }


_health_cache = {"at": 0.0, "problems": []}


def _runtime_problems() -> list:
    """Masalah lingkungan yang membuat transkripsi pasti gagal (di-cache 60 detik)."""
    if time.time() - _health_cache["at"] < 60:
        return _health_cache["problems"]
    problems = []
    if not check_ffmpeg().get("ok"):
        problems.append("ffmpeg tidak tersedia")
    if str(TRANSCRIPTION_RUNTIME.get("device", "")).startswith("cuda"):
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() < 1:
                problems.append("GPU CUDA tidak terdeteksi")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"ctranslate2/CUDA tidak dapat dipakai: {type(exc).__name__}")
    _health_cache.update(at=time.time(), problems=problems)
    return problems


@app.get("/healthz")
def healthz():
    problems = _runtime_problems()
    if problems:
        return JSONResponse({"ok": False, "problems": problems}, status_code=503)
    return {"ok": True}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), _user: dict = Depends(get_current_user)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            400,
            f"Ekstensi {ext or '(kosong)'} tidak didukung. "
            f"Izinkan: {', '.join(sorted(ALLOWED_EXT))}",
        )

    upload_dir = _user_upload_dir(_user)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(file.filename or "audio")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    stem_ = Path(safe_name).stem
    suffix = Path(safe_name).suffix
    for index in range(1, 1_000_000):
        candidate = safe_name if index == 1 else f"{stem_}-{index}{suffix}"
        dest = upload_dir / candidate
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
    except BaseException:
        # Batas ukuran, disk penuh, atau klien terputus: jangan tinggalkan potongan berkas.
        dest.unlink(missing_ok=True)
        raise

    return {"path": str(dest), "filename": dest.name, "size": size}


# ── Transcribe ───────────────────────────────────────────────────────────
@app.post("/api/transcribe")
def start_transcribe(body: dict, _user: dict = Depends(get_current_user)):
    audio_path = body.get("audio_path") or body.get("file_path")
    if not audio_path:
        raise HTTPException(400, "audio_path wajib diisi")

    model = body.get("model", "medium")
    language = body.get("language", "auto")
    if model not in ALLOWED_MODELS:
        raise HTTPException(400, f"Model tidak valid. Pilih: {', '.join(sorted(ALLOWED_MODELS))}")
    if language not in ALLOWED_LANGUAGES:
        raise HTTPException(400, "Bahasa tidak valid. Pilih: id, en, atau auto")

    audio_path = _validate_upload_path(audio_path)
    if not Path(audio_path).resolve().is_relative_to(_user_upload_dir(_user).resolve()):
        raise HTTPException(404, "File audio tidak ditemukan")
    output_dir = _user_result_dir(_user)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "model": model,
        "language": language,
        **TRANSCRIPTION_RUNTIME,
        "with_md": False,
        "output_dir": TranscribeEngine.reserve_folder(Path(audio_path).stem, output_dir),
    }

    try:
        save_config({"model": model, "language": language,
                     "device": config["device"], "compute_type": config["compute_type"]},
                    owner_id=_owner_id(_user))
    except OSError:
        pass  # gagal simpan bukan error fatal

    job = jobs.create(audio_path, config, owner_id=_owner_id(_user))
    if job is None:
        # Folder hasil dipesan sebelum mencoba slot worker; lepaskan bila job ditolak.
        try:
            reserved = Path(config["output_dir"])
            if reserved.is_dir() and not any(reserved.iterdir()):
                reserved.rmdir()
        except OSError:
            pass
        raise HTTPException(409, "Worker sedang digunakan. Coba lagi setelah transkripsi aktif selesai.")
    return job.to_dict()



@app.post("/api/jobs/{job_id}/resume")
def job_resume(job_id: str, _user: dict = Depends(get_current_user)):
    """Lanjutkan transkripsi yang gagal/terhenti dari titik simpan terakhir."""
    from src.core.engine import has_checkpoint
    row = job_store.get(job_id, _owner_id(_user))
    if not row or row["kind"] != "transcribe":
        raise HTTPException(404, "Job tidak ditemukan")
    if row["status"] not in {"error", "interrupted"}:
        raise HTTPException(409, "Hanya transkripsi yang gagal atau terhenti yang dapat dilanjutkan")
    config = json.loads(row.get("config_json") or "{}")
    output_dir = config.get("output_dir")
    audio_path = row["audio_path"]
    uploads = _user_upload_dir(_user).resolve()
    results = _user_result_dir(_user).resolve()
    if not output_dir or not _within_directory(output_dir, results) or not has_checkpoint(output_dir):
        raise HTTPException(410, "Titik simpan sudah tidak ada; unggah ulang rekamannya")
    if not _within_directory(audio_path, uploads) or not os.path.isfile(audio_path):
        raise HTTPException(410, "Berkas audio sudah dihapus; unggah ulang rekamannya")
    job = jobs.create(audio_path, {**config, "resume": True}, owner_id=_owner_id(_user))
    if job is None:
        raise HTTPException(409, "Worker sedang digunakan. Coba lagi setelah transkripsi aktif selesai.")
    return job.to_dict()


@app.get("/api/jobs/active")
def active_jobs(_user: dict = Depends(get_current_user)):
    """Job aktif untuk recovery setelah browser refresh."""
    return {"items": jobs.active(_owner_id(_user))}


@app.get("/api/jobs/worker-status")
def worker_status(_user: dict = Depends(get_current_user)):
    """Status worker tunggal tanpa mengekspos job atau pemiliknya."""
    return {"busy": job_store.worker_busy()}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, _user: dict = Depends(get_current_user)):
    job = jobs.get(job_id, _owner_id(_user))
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    return job.to_dict() if hasattr(job, "to_dict") else dict(job)


# Setiap tab yang memantau progres menahan satu thread selama menunggu event.
# Dengan kolam sendiri, thread bawaan FastAPI (~40) tetap bebas untuk endpoint lain.
_SSE_POOL = ThreadPoolExecutor(max_workers=128, thread_name_prefix="sse")


async def _stream_in_own_pool(sync_gen):
    loop = asyncio.get_running_loop()
    try:
        while True:
            chunk = await loop.run_in_executor(_SSE_POOL, next, sync_gen, None)
            if chunk is None:
                break
            yield chunk
    finally:
        try:
            sync_gen.close()
        except ValueError:
            pass  # masih menunggu event; berhenti sendiri pada heartbeat berikutnya


@app.get("/api/jobs/{job_id}/stream")
def job_stream(job_id: str, after: int = 0, _user: dict = Depends(get_current_user)):
    """Stream event job. `after` = jumlah event yang sudah diterima (untuk sambung ulang)."""
    if not jobs.get(job_id, _owner_id(_user)):
        raise HTTPException(404, "Job tidak ditemukan")
    return StreamingResponse(
        _stream_in_own_pool(jobs.event_stream(job_id, _owner_id(_user), after=after)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str, _user: dict = Depends(get_current_user)):
    ok = jobs.cancel(job_id, _owner_id(_user))
    if not ok:
        raise HTTPException(404, "Job tidak ditemukan")
    return {"ok": True}




@app.post("/api/notulen/ai")
def notulen_ai(body: dict, _user: dict = Depends(get_current_user)):
    """Buat notulen AI dari transkrip di folder hasil → DOCX."""
    if not AI_ENABLED:
        raise HTTPException(503, "Fitur AI notulen dimatikan di server ini (AI_ENABLED=false)")
    output_dir = body.get("output_dir") or body.get("folder") or body.get("folder_name")
    if not output_dir:
        raise HTTPException(400, "output_dir wajib diisi")
    fpath = _result_folder_for_user(Path(output_dir).name, _owner_id(_user))
    resolved = fpath.resolve()
    if not fpath.is_dir():
        raise HTTPException(404, "Folder hasil tidak ditemukan")
    if not resolved.is_relative_to(_user_result_dir(_user).resolve()):
        raise HTTPException(404, "Folder hasil tidak ditemukan")
    return jobs.create_ai(str(fpath), owner_id=_owner_id(_user)).to_dict()

TEXT_EXT = {".txt", ".md"}
MAX_TEXT_BYTES = _env_int("MAX_TEXT_BYTES", 5 * 1024**2)


def _decode_text_upload(data: bytes) -> str:
    """Baca berkas teks unggahan: UTF-8 (dengan/tanpa BOM), lalu Windows-1252."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(400, "Berkas teks tidak dapat dibaca. Simpan sebagai UTF-8.")


@app.post("/api/notulen/from-text")
async def notulen_from_text(file: UploadFile = File(...), _user: dict = Depends(get_current_user)):
    """Unggah transkrip teks (.txt/.md) lalu susun notulen AI darinya."""
    if not AI_ENABLED:
        raise HTTPException(503, "Fitur AI notulen dimatikan di server ini (AI_ENABLED=false)")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in TEXT_EXT:
        raise HTTPException(400, f"Ekstensi {ext or '(kosong)'} tidak didukung. Izinkan: .md, .txt")

    data = await file.read(MAX_TEXT_BYTES + 1)
    if len(data) > MAX_TEXT_BYTES:
        raise HTTPException(413, f"Berkas teks melebihi batas {MAX_TEXT_BYTES // 1024**2} MB")
    text = _decode_text_upload(data).replace("\x00", "").strip()
    if not text:
        raise HTTPException(400, "Berkas teks kosong")

    output_root = _user_result_dir(_user)
    output_root.mkdir(parents=True, exist_ok=True)
    stem_ = Path(_sanitize_filename(file.filename or "teks")).stem or "teks"
    folder = Path(TranscribeEngine.reserve_folder(stem_, output_root))
    try:
        (folder / "transkrip.txt").write_text(text + "\n", encoding="utf-8")
        job = jobs.create_ai(str(folder), owner_id=_owner_id(_user))
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return {**job.to_dict(), "folder_name": folder.name}


@app.get("/api/documents/types")
def document_types(_user: dict = Depends(get_current_user)):
    """Jenis dokumen resmi dan isian kepalanya, dibaca antarmuka."""
    from src.pandora_documents.layanan import daftar_jenis
    return {"items": daftar_jenis()}


@app.post("/api/documents/generate")
def document_generate(body: dict, _user: dict = Depends(get_current_user)):
    """Susun dokumen resmi (naskah dinas) dari transkrip di folder hasil → MD, DOCX, PDF."""
    if not AI_ENABLED:
        raise HTTPException(503, "Fitur AI dimatikan di server ini (AI_ENABLED=false)")
    from src.pandora_documents.layanan import bersihkan_isian, daftar_jenis
    folder = body.get("folder_name") or body.get("output_dir")
    if not folder or not isinstance(folder, str):
        raise HTTPException(400, "folder_name wajib diisi")
    fpath = _result_folder_for_user(Path(folder).name, _owner_id(_user))
    if not fpath.is_dir() or not fpath.resolve().is_relative_to(_user_result_dir(_user).resolve()):
        raise HTTPException(404, "Folder hasil tidak ditemukan")
    jenis = body.get("jenis", "laporan_kegiatan")
    rencana = {item["jenis"]: item for item in daftar_jenis()}
    if jenis not in rencana:
        raise HTTPException(400, "Jenis dokumen tidak dikenal")
    isian = body.get("kepala") if isinstance(body.get("kepala"), dict) else {}
    kepala = {item["kunci"]: bersihkan_isian(isian.get(item["kunci"]))
              for item in rencana[jenis]["kepala"]}
    return jobs.create_document(str(fpath), jenis=jenis, judul=bersihkan_isian(body.get("judul")),
                                kepala=kepala, owner_id=_owner_id(_user)).to_dict()


@app.post("/api/transcript/cleanup")
def transcript_cleanup(body: dict, _user: dict = Depends(get_current_user)):
    """Rapikan transkrip dengan AI tanpa mengubah file transkrip asli."""
    if not AI_ENABLED:
        raise HTTPException(
            503,
            "Fitur AI dimatikan di server ini (AI_ENABLED=false)",
        )
    output_dir = body.get("output_dir") or body.get("folder") or body.get("folder_name")
    if not output_dir:
        raise HTTPException(400, "output_dir wajib diisi")
    fpath = _result_folder_for_user(Path(output_dir).name, _owner_id(_user))
    resolved = fpath.resolve()
    if not fpath.is_dir():
        raise HTTPException(404, "Folder hasil tidak ditemukan")
    if not resolved.is_relative_to(_user_result_dir(_user).resolve()):
        raise HTTPException(404, "Folder hasil tidak ditemukan")
    return jobs.create_cleanup(str(fpath), owner_id=_owner_id(_user)).to_dict()


# ── History (hasil transkripsi) ──────────────────────────────────────────
@app.get("/api/history")
def history(_user: dict = Depends(get_current_user)):
    items = []
    result_root = _user_result_dir(_user)
    for folder in list_history(result_root):
        folder_path = Path(folder)
        resolved_folder = folder_path.resolve()
        if not resolved_folder.is_relative_to(result_root.resolve()):
            continue
        files = [f.name for f in resolved_folder.iterdir()
                 if f.is_file() and (
                     not f.name.lower().endswith(".md")
                     or f.name in {"notulen_ai.md", "transkrip_rapi_ai.md",
                                   "dokumen_laporan_kegiatan.md", "dokumen_notulen_rapat.md"}
                 )]
        if not files:
            continue  # folder yang baru dipesan job antre, belum ada hasilnya
        files.sort(key=lambda n: (n.startswith("transkrip"), n))
        items.append({"name": resolved_folder.name, "files": files})
    return {"items": items}


@app.get("/api/admin/archive")
def legacy_archive(_user: dict = Depends(get_current_user)):
    if not is_archive_admin(_user):
        raise HTTPException(403, "Akses arsip lama hanya untuk admin")
    archive_root = (HASIL_DIR / "_archive_legacy").resolve()
    if not archive_root.is_relative_to(HASIL_DIR.resolve()) or not archive_root.is_dir():
        return {"items": []}
    return {"items": [{"name": item.name} for item in sorted(archive_root.iterdir()) if item.is_dir()]}


@app.get("/api/admin/archive/{folder_name}/file/{file_name}")
def legacy_archive_file(folder_name: str, file_name: str, download: bool = False,
                        _user: dict = Depends(get_current_user)):
    if not is_archive_admin(_user):
        raise HTTPException(403, "Akses arsip lama hanya untuk admin")
    if not re.fullmatch(r"\d{2,}_[\w\- ]+", folder_name):
        raise HTTPException(404, "File tidak ditemukan")
    root = (HASIL_DIR / "_archive_legacy").resolve()
    folder = (root / folder_name).resolve()
    name = os.path.basename(file_name)
    path = (folder / name).resolve()
    if not folder.is_relative_to(root) or not path.is_relative_to(folder) or not path.is_file():
        raise HTTPException(404, "File tidak ditemukan")
    if download:
        return FileResponse(path, filename=path.name)
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(415, "Preview hanya mendukung file teks; gunakan unduh")
    return {"name": path.name, "content": content, "size": path.stat().st_size}

@app.delete("/api/history/{folder_name}")
def delete_history(folder_name: str, _user: dict = Depends(get_current_user)):
    """Hapus satu folder hasil yang dipilih dari history."""
    if not re.fullmatch(r"\d{2,}_[\w.\- ]+", folder_name):
        raise HTTPException(400, "Nama folder tidak valid")
    folder = _result_folder_for_user(folder_name, _owner_id(_user))
    if not folder.is_dir():
        raise HTTPException(404, "Folder hasil tidak ditemukan")
    import shutil
    shutil.rmtree(folder)
    return {"ok": True, "deleted": folder_name}


@app.get("/api/history/{folder_name}/file/{file_name}")
def history_file(folder_name: str, file_name: str, download: bool = False, _user: dict = Depends(get_current_user)):
    if not re.fullmatch(r"\d{2,}_[\w.\- ]+", folder_name):
        raise HTTPException(400, "Nama folder tidak valid")
    file_name = os.path.basename(file_name)
    folder = _result_folder_for_user(folder_name, _owner_id(_user))
    fpath = (folder / file_name).resolve()
    if not fpath.is_relative_to(_user_result_dir(_user).resolve()) or not fpath.is_relative_to(folder):
        raise HTTPException(404, "File tidak ditemukan")
    if not folder.is_dir():
        raise HTTPException(404, "Folder hasil tidak ditemukan")

    transcript_stem = re.sub(r"[^\w.\- ]", "", folder_name).strip()[:50] or "transkrip"
    legacy_transcript_stem = re.sub(r"[^\w\- ]", "", folder_name).strip()[:50] or "transkrip"
    transcript_docx_names = {
        f"Transkrip_{folder_name}.docx",
        f"Transkrip_{transcript_stem}.docx",
        f"Transkrip_{legacy_transcript_stem}.docx",
    }
    if download and file_name in transcript_docx_names and not fpath.exists():
        transcript_path = (folder / "transkrip.txt").resolve()
        if not transcript_path.is_relative_to(_user_result_dir(_user).resolve()) or not transcript_path.is_file():
            raise HTTPException(404, "Transkrip asli tidak ditemukan")
        try:
            from docx import Document
        except ImportError as exc:
            raise HTTPException(503, "Generator DOCX tidak tersedia") from exc

        document = Document()
        document.add_heading(f"Transkrip — {folder_name}", level=1)
        transcript_text = " ".join(
            line.strip() for line in transcript_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        document.add_paragraph(transcript_text)
        document.add_paragraph(CATATAN_TRANSKRIP)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            document.save(temp_path)
            return FileResponse(
                temp_path,
                filename=f"Transkrip_{folder_name}.docx",
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                background=BackgroundTask(temp_path.unlink, missing_ok=True),
            )
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    if not fpath.is_file():
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
    print("  PANDORA — CONVERSATIONS WORTH KEEPING")
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
    parser = argparse.ArgumentParser(description="Pandora — audio transcription workspace")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind host (default 127.0.0.1; 0.0.0.0 = semua)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true",
                        help="Jangan buka browser otomatis")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)
