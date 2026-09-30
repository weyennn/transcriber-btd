"""Path helpers — konsisten dengan struktur output v3.

DATA_DIR (env): jika diset (Docker), semua state dialihkan ke sana:
    HASIL_DIR  = DATA_DIR/hasil
    UPLOAD_DIR = DATA_DIR/uploads
Jika tidak diset: perilaku lama (relatif project root) — Windows dev.
"""

import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_DATA_DIR = os.environ.get("DATA_DIR", "").strip()
if _DATA_DIR:
    HASIL_DIR = Path(_DATA_DIR) / "hasil"
    UPLOAD_DIR = Path(_DATA_DIR) / "uploads"
else:
    HASIL_DIR = PROJECT_ROOT / "transcribe_hasil"
    UPLOAD_DIR = PROJECT_ROOT / "uploads"


def project_root() -> Path:
    return PROJECT_ROOT


def stem(path: str) -> str:
    """Filename tanpa extension ganda.  audio.mp3.mpeg -> audio."""
    name = os.path.splitext(os.path.basename(path))[0]
    while True:
        root, ext = os.path.splitext(name)
        if ext == "":
            break
        name = root
    return name


_OWNER_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_RESULT_FOLDER_RE = re.compile(r"^\d{2}_[\w.\- ]+$")


def _owner_root(root: Path, owner_id: str) -> Path:
    """Return a storage namespace without accepting path-like owner input."""
    if owner_id == "legacy":
        return root
    if not isinstance(owner_id, str) or not _OWNER_ID_RE.fullmatch(owner_id):
        raise ValueError("owner_id tidak valid")
    return root / owner_id


def upload_dir_for(owner_id: str) -> Path:
    return _owner_root(UPLOAD_DIR, owner_id)


def result_dir_for(owner_id: str) -> Path:
    return _owner_root(HASIL_DIR, owner_id)


def auto_folder(audio_stem: str, result_dir: Path | None = None) -> str:
    """Allocate XX_name below one result namespace, never the shared root."""
    root = result_dir or HASIL_DIR
    pattern = re.compile(r"^(\d{2})_.*$")
    max_n = 0
    if root.is_dir():
        for entry in os.listdir(root):
            m = pattern.match(entry)
            if m and (root / entry).is_dir():
                max_n = max(max_n, int(m.group(1)))
    return str(root / f"{max_n + 1:02d}_{audio_stem}")


def list_history(result_dir: Path | None = None) -> list:
    """List result folders in one namespace, newest folder name first."""
    root = result_dir or HASIL_DIR
    if not root.is_dir():
        return []
    folders = [d for d in root.iterdir() if d.is_dir() and _RESULT_FOLDER_RE.fullmatch(d.name)]
    folders.sort(key=lambda p: p.name, reverse=True)
    return [str(p) for p in folders]
