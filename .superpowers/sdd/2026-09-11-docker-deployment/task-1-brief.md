### Task 1: `paths.py` — DATA_DIR override + UPLOAD_DIR

**Files:**
- Modify: `src/utils/paths.py`
- Test: `tests/test_paths.py` (baru)

**Interfaces:**
- Produces: `HASIL_DIR: Path`, `UPLOAD_DIR: Path` (keduanya menghormati env `DATA_DIR`), `list_history() -> list[str]` (tidak berubah). Task 2 (`server.py`) meng-import `UPLOAD_DIR` dari sini; `engine.py` (Task 3) meng-import `HASIL_DIR` dari sini.

- [ ] **Step 1: Tulis failing test**

Buat `tests/test_paths.py`:

```python
"""Test DATA_DIR override pada paths (Docker deployment)."""
import importlib
import os


def _reload_paths(monkeypatch, data_dir=None):
    if data_dir is None:
        monkeypatch.delenv("DATA_DIR", raising=False)
    else:
        monkeypatch.setenv("DATA_DIR", data_dir)
    import src.utils.paths as paths
    importlib.reload(paths)
    return paths


def test_default_tanpa_env(monkeypatch):
    """Tanpa DATA_DIR: perilaku lama — relatif project root."""
    paths = _reload_paths(monkeypatch)
    assert paths.HASIL_DIR == paths.PROJECT_ROOT / "transcribe_hasil"
    assert paths.UPLOAD_DIR == paths.PROJECT_ROOT / "uploads"


def test_data_dir_override(monkeypatch):
    paths = _reload_paths(monkeypatch, "/data")
    assert str(paths.HASIL_DIR) == "/data/hasil"
    assert str(paths.UPLOAD_DIR) == "/data/uploads"


def test_env_kosong_diabaikan(monkeypatch):
    """DATA_DIR string kosong = tidak diset (fallback perilaku lama)."""
    paths = _reload_paths(monkeypatch, "")
    assert paths.HASIL_DIR == paths.PROJECT_ROOT / "transcribe_hasil"
```

- [ ] **Step 2: Jalankan test, verifikasi FAIL**

Run: `python3 -m pytest tests/test_paths.py -v` (pakai python3 system atau buat venv-mac sementara; test ini murni stdlib, tidak butuh deps berat)
Expected: FAIL — `AttributeError: module 'src.utils.paths' has no attribute 'UPLOAD_DIR'`

- [ ] **Step 3: Implementasi**

Patch `src/utils/paths.py` bagian atas:

```python
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
```

Sisa file (`project_root()`, `stem()`, `auto_folder()`, `list_history()`) tidak berubah.

- [ ] **Step 4: Jalankan test, verifikasi PASS**

Run: `python3 -m pytest tests/test_paths.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/utils/paths.py tests/test_paths.py
git commit -m "feat: DATA_DIR env override untuk HASIL_DIR/UPLOAD_DIR"
```

---