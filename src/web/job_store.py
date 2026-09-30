"""Persistent SQLite state for background jobs."""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

_config_dir = os.environ.get("CONFIG_DIR", "").strip()
_data_dir = os.environ.get("DATA_DIR", "").strip()
DB_PATH = (
    Path(_config_dir) / "jobs.sqlite3" if _config_dir
    else Path(_data_dir) / "config" / "jobs.sqlite3" if _data_dir
    else Path("config") / "jobs.sqlite3"
)
_lock = threading.RLock()


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init():
    with _lock, _connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, audio_path TEXT NOT NULL,
            config_json TEXT NOT NULL, status TEXT NOT NULL, output_dir TEXT,
            metadata_json TEXT, error TEXT, progress INTEGER NOT NULL DEFAULT 0,
            message TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
            owner_id TEXT NOT NULL DEFAULT 'legacy'
        )""")
        columns = {row[1] for row in c.execute("PRAGMA table_info(jobs)")}
        if "owner_id" not in columns:
            c.execute("ALTER TABLE jobs ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'legacy'")
        c.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, updated_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_jobs_owner ON jobs(owner_id, created_at)")
        c.execute("UPDATE jobs SET status='interrupted', message='Proses terhenti karena service restart' WHERE status IN ('pending','running')")


def create(job):
    now = time.time()
    with _lock, _connect() as c:
        c.execute("""INSERT INTO jobs
            (id,kind,audio_path,config_json,status,output_dir,metadata_json,error,
             progress,message,created_at,updated_at,owner_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (job.id, job.kind, job.audio_path, json.dumps(job.config), job.status,
             None, None, None, 0, "Menunggu worker...", now, now,
             getattr(job, "owner_id", "legacy")))


def update(job, **fields):
    if not fields:
        return
    fields["updated_at"] = time.time()
    columns = ", ".join(f"{k}=?" for k in fields)
    values = [json.dumps(v, ensure_ascii=False) if k == "metadata_json" else v for k, v in fields.items()]
    with _lock, _connect() as c:
        c.execute(f"UPDATE jobs SET {columns} WHERE id=?", values + [job.id])


def active(owner_id="legacy"):
    with _lock, _connect() as c:
        rows = c.execute("SELECT * FROM jobs WHERE owner_id=? AND status IN ('pending','running') ORDER BY created_at DESC", (owner_id,)).fetchall()
    return [dict(row) for row in rows]


def queue_status():
    """Aggregate worker counts without exposing job ownership or paths."""
    with _lock, _connect() as c:
        rows = c.execute(
            "SELECT status, COUNT(*) AS count FROM jobs "
            "WHERE status IN ('pending', 'running') GROUP BY status"
        ).fetchall()
    counts = {row["status"]: int(row["count"]) for row in rows}
    running_count = counts.get("running", 0)
    pending_count = counts.get("pending", 0)
    return {
        "running_count": running_count,
        "pending_count": pending_count,
        "total_count": running_count + pending_count,
        "worker_busy": running_count > 0,
    }


def queue_position(job_id):
    """Return count of active jobs ahead of this job, without exposing them."""
    with _lock, _connect() as c:
        row = c.execute(
            "SELECT created_at, status FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        if not row or row["status"] not in ("pending", "running"):
            return None
        ahead = c.execute(
            "SELECT COUNT(*) FROM jobs WHERE status IN ('pending','running') "
            "AND (created_at < ? OR (created_at = ? AND id < ?))",
            (row["created_at"], row["created_at"], job_id),
        ).fetchone()[0]
        return {"ahead": int(ahead), "status": row["status"]}


def get(job_id, owner_id=None):
    with _lock, _connect() as c:
        if owner_id is None:
            row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        else:
            row = c.execute("SELECT * FROM jobs WHERE id=? AND owner_id=?", (job_id, owner_id)).fetchone()
    return dict(row) if row else None


def as_dict(row):
    if not row:
        return None
    row["config"] = json.loads(row.pop("config_json") or "{}")
    row["metadata"] = json.loads(row.pop("metadata_json") or "null")
    return row
