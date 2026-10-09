"""JobManager — transkripsi background di server web.

Setiap job:
  - id unik
  - thread sendiri yang memanggil TranscribeEngine.transcribe
  - queue event thread-safe (untuk SSE streaming ke browser)
  - cancel_event untuk pembatalan

Event queue item (dict):
    {"type": "log", "message": str}
    {"type": "progress", "percent": int, "message": str}
    {"type": "segment", "start": float, "end": float, "text": str}
    {"type": "finished", "output_dir": str, "metadata": dict}
    {"type": "error", "error": str}
    {"type": "cancelled"}
"""

import queue
import threading
import time
import uuid

from src.core.engine import CancelledError, TranscribeEngine
from pathlib import Path

from src.web import job_store

HEARTBEAT_SECONDS = 15
job_store.init()


class TranscribeJob:
    """Satu pekerjaan: transcribe, ai_cleanup, ai_notulen, atau ai_document."""

    def __init__(self, job_id, audio_path, config, kind="transcribe", owner_id="legacy"):
        self.id = job_id
        self.kind = kind
        self.owner_id = owner_id
        self.audio_path = audio_path  # untuk kind=ai_*: folder hasil (output_dir)
        self.config = config
        self.status = "pending"  # pending|running|done|error|cancelled
        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.output_dir = None
        self.metadata = None
        self.error = None
        self.created_at = time.time()
        self.thread = None

    def to_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "config": self.config,
            "output_dir": Path(self.output_dir).name if self.output_dir else None,
            "metadata": self.metadata,
            "error": self.error,
            "created_at": self.created_at,
        }


class JobManager:
    """Registry + lifecycle semua job."""

    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()
        self._worker_slot = threading.Semaphore(1)

    def create(self, audio_path, config, owner_id="legacy") -> TranscribeJob:
        job_id = uuid.uuid4().hex[:12]
        job = TranscribeJob(job_id, audio_path, config, owner_id=owner_id)
        with self._lock:
            self._jobs[job_id] = job
        job_store.create(job)

        job.thread = threading.Thread(
            target=self._run, args=(job,), daemon=True, name=f"transcribe-{job_id}"
        )
        job.thread.start()
        return job

    def create_cleanup(self, output_dir, owner_id="legacy") -> TranscribeJob:
        """Job rapikan AI: bersihkan transkrip di output_dir → TXT."""
        job_id = uuid.uuid4().hex[:12]
        job = TranscribeJob(job_id, output_dir, {}, kind="ai_cleanup", owner_id=owner_id)
        with self._lock:
            self._jobs[job_id] = job
        job_store.create(job)
        job.thread = threading.Thread(
            target=self._run_cleanup, args=(job,), daemon=True, name=f"cleanup-{job_id}"
        )
        job.thread.start()
        return job

    def create_ai(self, output_dir, owner_id="legacy") -> TranscribeJob:
        """Job notulen AI: rangkum transkrip di output_dir → DOCX."""
        job_id = uuid.uuid4().hex[:12]
        job = TranscribeJob(job_id, output_dir, {}, kind="ai_notulen", owner_id=owner_id)
        with self._lock:
            self._jobs[job_id] = job
        job_store.create(job)

        job.thread = threading.Thread(
            target=self._run_ai, args=(job,), daemon=True, name=f"ai-{job_id}"
        )
        job.thread.start()
        return job

    def create_document(self, output_dir, jenis="laporan_kegiatan", judul="",
                        kepala=None, owner_id="legacy") -> TranscribeJob:
        """Job dokumen resmi: susun naskah dinas dari transkrip di output_dir → MD, DOCX, PDF."""
        job_id = uuid.uuid4().hex[:12]
        config = {"jenis": jenis, "judul": judul, "kepala": kepala or {}}
        job = TranscribeJob(job_id, output_dir, config, kind="ai_document", owner_id=owner_id)
        with self._lock:
            self._jobs[job_id] = job
        job_store.create(job)
        job.thread = threading.Thread(
            target=self._run_document, args=(job,), daemon=True, name=f"document-{job_id}"
        )
        job.thread.start()
        return job

    def get(self, job_id, owner_id=None):
        with self._lock:
            job = self._jobs.get(job_id)
            if job and (owner_id is None or job.owner_id == owner_id):
                return job
        row = job_store.get(job_id, owner_id)
        return job_store.as_dict(row) if row else None

    def active(self, owner_id):
        """Job aktif dari registry RAM, dengan fallback metadata SQLite."""
        with self._lock:
            live = [job.to_dict() for job in self._jobs.values()
                    if job.owner_id == owner_id and job.status in {"pending", "running"}]
        if live:
            return live
        return [job_store.as_dict(row) for row in job_store.active(owner_id)]

    def cancel(self, job_id, owner_id) -> bool:
        job = self.get(job_id, owner_id)
        if not job or not hasattr(job, "cancel_event"):
            return False
        job.cancel_event.set()
        return True

    def _run(self, job):
        with self._worker_slot:
            self._run_transcribe(job)

    def _run_transcribe(self, job):
        job.status = "running"
        job_store.update(job, status=job.status, message="Transkripsi berjalan")
        job.events.put({"type": "log", "message": f"Job {job.id} dimulai."})

        def on_log(msg):
            job.events.put({"type": "log", "message": msg})

        def on_progress(pct, msg):
            job_store.update(job, progress=pct, message=msg)
            job.events.put({"type": "progress", "percent": pct, "message": msg})

        def on_segment(start, end, text):
            job.events.put({"type": "segment", "start": start, "end": end, "text": text})
            if job.cancel_event.is_set():
                raise CancelledError()
        def on_finished(out_dir, metadata):
            job.output_dir = out_dir
            job.metadata = metadata
            job.events.put({"type": "finished", "output_dir": Path(out_dir).name,
                            "metadata": metadata})

        def on_error(err):
            job.error = err
            job.events.put({"type": "error", "error": err})

        callbacks = {
            "on_log": on_log,
            "on_progress": on_progress,
            "on_segment": on_segment,
            "on_finished": on_finished,
            "on_error": on_error,
        }

        try:
            TranscribeEngine.transcribe(job.audio_path, job.config, callbacks)
            if job.status != "cancelled":
                job.status = "done"
        except CancelledError:
            job.status = "cancelled"
            job_store.update(job, status=job.status, message="Dibatalkan")
            job.events.put({"type": "cancelled"})
        except Exception as e:  # noqa: BLE001
            job.status = "error"
            job.error = str(e)
            job_store.update(job, status=job.status, error=job.error, message="Gagal")
            job.events.put({"type": "error", "error": f"{type(e).__name__}: {e}"})

        terminal_fields = {"status": job.status, "output_dir": job.output_dir,
                           "metadata_json": job.metadata, "error": job.error}
        if job.status == "done":
            terminal_fields["progress"] = 100
        job_store.update(job, **terminal_fields)
        # Penanda akhir stream (SSE generator berhenti setelah ini)
        job.events.put({"type": "job_end", "status": job.status})

    # ── Runner AI cleanup ──────────────────────────────────────────────
    def _run_cleanup(self, job):
        with self._worker_slot:
            job.status = "running"
            job_store.update(job, status=job.status, message="AI sedang merapikan transkrip")
            job.events.put({"type": "log", "message": f"Job rapikan AI {job.id} dimulai."})

            def on_log(msg):
                job.events.put({"type": "log", "message": msg})

            def on_progress(pct, msg):
                job_store.update(job, progress=pct, message=msg)
                job.events.put({"type": "progress", "percent": pct, "message": msg})

            def on_finished(result):
                job.output_dir = job.audio_path
                job.metadata = result
                job.events.put({"type": "finished", "output_dir": Path(job.output_dir).name,
                                "metadata": result})

            def on_error(err):
                job.error = err
                job.events.put({"type": "error", "error": err})

            try:
                from src.notulen.ai_generator import generate_cleanup
                generate_cleanup(job.audio_path, {
                    "on_log": on_log, "on_progress": on_progress,
                    "on_finished": on_finished, "on_error": on_error,
                    "cancel_event": job.cancel_event,
                })
                job.status = "done"
            except CancelledError:
                job.status = "cancelled"
                job_store.update(job, status=job.status, message="Dibatalkan")
                job.events.put({"type": "cancelled"})
            except Exception as e:  # noqa: BLE001
                job.status = "error"
                job.error = str(e)
                job.events.put({"type": "error", "error": f"{type(e).__name__}: {e}"})
            job_store.update(job, status=job.status, output_dir=job.output_dir,
                             metadata_json=job.metadata, error=job.error,
                             progress=100 if job.status == "done" else 0)
            job.events.put({"type": "job_end", "status": job.status})

    # ── Runner dokumen resmi ───────────────────────────────────────────
    def _run_document(self, job):
        with self._worker_slot:
            job.status = "running"
            job_store.update(job, status=job.status, message="AI sedang menyusun dokumen resmi")
            job.events.put({"type": "log", "message": f"Job dokumen resmi {job.id} dimulai."})

            def on_log(msg):
                job.events.put({"type": "log", "message": msg})

            def on_progress(pct, msg):
                job_store.update(job, progress=pct, message=msg)
                job.events.put({"type": "progress", "percent": pct, "message": msg})

            def on_finished(result):
                job.output_dir = job.audio_path
                job.metadata = result
                job.events.put({"type": "finished", "output_dir": Path(job.output_dir).name,
                                "metadata": result})

            try:
                from src.pandora_documents.layanan import susun_dokumen
                susun_dokumen(job.audio_path, job.config.get("jenis", "laporan_kegiatan"),
                              job.config.get("judul", ""), job.config.get("kepala"), {
                    "on_log": on_log, "on_progress": on_progress,
                    "on_finished": on_finished,
                    "cancel_event": job.cancel_event,
                })
                job.status = "done"
            except CancelledError:
                job.status = "cancelled"
                job_store.update(job, status=job.status, message="Dibatalkan")
                job.events.put({"type": "cancelled"})
            except Exception as e:  # noqa: BLE001
                job.status = "error"
                job.error = str(e)
                job.events.put({"type": "error", "error": job.error})
            job_store.update(job, status=job.status, output_dir=job.output_dir,
                             metadata_json=job.metadata, error=job.error,
                             progress=100 if job.status == "done" else 0)
            job.events.put({"type": "job_end", "status": job.status})

    # ── Runner notulen AI ──────────────────────────────────────────────
    def _run_ai(self, job):
        with self._worker_slot:
            self._run_ai_job(job)

    def _run_ai_job(self, job):
        job.status = "running"
        job_store.update(job, status=job.status, message="AI sedang menyusun notulen")
        job.events.put({"type": "log", "message": f"Job AI {job.id} dimulai."})

        def on_log(msg):
            job.events.put({"type": "log", "message": msg})

        def on_progress(pct, msg):
            job_store.update(job, progress=pct, message=msg)
            job.events.put({"type": "progress", "percent": pct, "message": msg})

        def on_finished(result):
            job.output_dir = job.audio_path
            job.metadata = result
            job.events.put({"type": "finished", "output_dir": Path(job.output_dir).name,
                            "metadata": result})

        def on_error(err):
            job.error = err
            job.events.put({"type": "error", "error": err})

        callbacks = {
            "on_log": on_log,
            "on_progress": on_progress,
            "on_finished": on_finished,
            "on_error": on_error,
        }

        try:
            from src.notulen.ai_generator import generate_notulen_docx
            generate_notulen_docx(job.audio_path, {**callbacks, "cancel_event": job.cancel_event})
            if job.status != "cancelled":
                job.status = "done"
        except CancelledError:
            job.status = "cancelled"
            job_store.update(job, status=job.status, message="Dibatalkan")
            job.events.put({"type": "cancelled"})
        except Exception as e:  # noqa: BLE001
            job.status = "error"
            job.error = str(e)
            job.events.put({"type": "error", "error": f"{type(e).__name__}: {e}"})

        terminal_fields = {"status": job.status, "output_dir": job.output_dir,
                           "metadata_json": job.metadata, "error": job.error}
        if job.status == "done":
            terminal_fields["progress"] = 100
        job_store.update(job, **terminal_fields)
        job.events.put({"type": "job_end", "status": job.status})

    # ── SSE generator ───────────────────────────────────────────────────
    def event_stream(self, job_id, owner_id=None):
        """Generator SSE for an owner-verified live job."""
        job = self.get(job_id, owner_id)
        if not job or not hasattr(job, "events"):
            yield "event: error\ndata: {\"error\": \"job tidak ditemukan\"}\n\n"
            return

        while True:
            try:
                item = job.events.get(timeout=HEARTBEAT_SECONDS)
            except queue.Empty:
                # heartbeat — jaga koneksi tetap hidup
                yield ": heartbeat\n\n"
                continue

            if item["type"] == "job_end":
                yield f"event: job_end\ndata: {_json(item)}\n\n"
                break

            yield f"event: {item['type']}\ndata: {_json(item)}\n\n"


def _json(obj):
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)
