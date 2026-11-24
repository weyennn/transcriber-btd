"""Retensi hasil: folder hasil dan riwayat job dihapus setelah RESULT_RETENTION_DAYS hari."""

import os
import re
import shutil
import time
from pathlib import Path

from src.utils import paths

DEFAULT_RETENTION_DAYS = 30
_RESULT_FOLDER = re.compile(r"^\d{2,}_[\w.\- ]+$")
_OWNER_DIR = re.compile(r"^[0-9a-f]{64}$")


def retention_days() -> int:
    """Hari penyimpanan hasil; 0 berarti penghapusan otomatis dimatikan.

    Tanpa pengaturan eksplisit, penghapusan hanya aktif di mode server/Docker
    (DATA_DIR diset). Menjalankan aplikasi lokal tidak menghapus folder hasil lama.
    """
    raw = os.environ.get("RESULT_RETENTION_DAYS", "").strip()
    if not raw:
        return DEFAULT_RETENTION_DAYS if os.environ.get("DATA_DIR", "").strip() else 0
    try:
        days = int(raw)
    except ValueError:
        return DEFAULT_RETENTION_DAYS if os.environ.get("DATA_DIR", "").strip() else 0
    return max(days, 0)


def _last_touched(folder: Path) -> float:
    newest = folder.stat().st_mtime
    for path in folder.rglob("*"):
        try:
            newest = max(newest, path.stat().st_mtime)
        except OSError:
            continue
    return newest


def _result_roots() -> list:
    root = paths.HASIL_DIR
    if not root.is_dir():
        return []
    roots = [root]
    roots += [d for d in root.iterdir() if d.is_dir() and _OWNER_DIR.fullmatch(d.name)]
    return roots


def purge_expired_results(days=None, now=None, dry_run=False) -> list:
    """Hapus folder hasil yang terakhir diubah lebih dari `days` hari lalu.

    Hanya menyentuh folder bernama `NN_nama` di akar hasil dan di folder pemilik;
    folder lain (mis. arsip lama) tidak dihapus. Mengembalikan daftar folder yang
    dihapus (atau akan dihapus bila dry_run).
    """
    days = retention_days() if days is None else days
    if days <= 0:
        return []
    cutoff = (now if now is not None else time.time()) - days * 86400
    removed = []
    for root in _result_roots():
        for folder in root.iterdir():
            if not folder.is_dir() or folder.is_symlink() or not _RESULT_FOLDER.fullmatch(folder.name):
                continue
            try:
                if _last_touched(folder) >= cutoff:
                    continue
                if not dry_run:
                    shutil.rmtree(folder)
                removed.append(str(folder))
            except OSError:
                continue
    return removed
