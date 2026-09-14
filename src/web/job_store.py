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
            message TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, updated_at)")
        c.execute("UPDATE jobs SET status='interrupted', message='Proses terhenti karena service restart' WHERE status IN ('pending','running')")


def create(job):
    now = time.time()
    with _lock, _connect() as c:
        c.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (job.id, job.kind, job.audio_path, json.dumps(job.config), job.status, None, None, None, 0, "Menunggu worker...", now, now))


def update(job, **fields):
    if not fields:
        return
    fields["updated_at"] = time.time()
    columns = ", ".join(f"{k}=?" for k in fields)
    values = [json.dumps(v, ensure_ascii=False) if k == "metadata_json" else v for k, v in fields.items()]
    with _lock, _connect() as c:
        c.execute(f"UPDATE jobs SET {columns} WHERE id=?", values + [job.id])


def active():
    with _lock, _connect() as c:
        rows = c.execute("SELECT * FROM jobs WHERE status IN ('pending','running') ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def get(job_id):
    with _lock, _connect() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def as_dict(row):
    if not row:
        return None
    row["config"] = json.loads(row.pop("config_json") or "{}")
    row["metadata"] = json.loads(row.pop("metadata_json") or "null")
    return row
