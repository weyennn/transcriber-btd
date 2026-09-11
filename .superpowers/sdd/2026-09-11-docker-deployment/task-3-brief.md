### Task 3: `engine.py` — HASIL_DIR dari paths.py (satu sumber kebenaran)

**Files:**
- Modify: `src/core/engine.py:26-28`
- Test: `tests/test_engine_paths.py` (baru)

**Interfaces:**
- Consumes: `src.utils.paths.HASIL_DIR` (Task 1)
- Produces: `TranscribeEngine.HASIL_DIR` tetap ada sebagai alias module-level (kode lain mungkin mereferensikannya) tapi nilainya = `paths.HASIL_DIR`. Tidak ada perubahan signature method.

- [ ] **Step 1: Tulis failing test**

Buat `tests/test_engine_paths.py`:

```python
"""Engine harus memakai HASIL_DIR dari paths.py (menghormati DATA_DIR)."""
import importlib
import os


def test_engine_hormati_data_dir(monkeypatch):
    monkeypatch.setenv("DATA_DIR", "/data")
    import src.utils.paths as paths
    importlib.reload(paths)
    import src.core.engine as engine
    importlib.reload(engine)
    assert str(engine.HASIL_DIR) == "/data/hasil"
```

- [ ] **Step 2: Jalankan test, verifikasi FAIL**

Run: `python3 -m pytest tests/test_engine_paths.py -v`
Expected: FAIL — `engine.HASIL_DIR` masih `<project>/transcribe_hasil`

- [ ] **Step 3: Implementasi**

Patch `src/core/engine.py:26-28`:

```python
# Root state: dari paths.py (menghormati env DATA_DIR di Docker)
from src.utils.paths import HASIL_DIR  # noqa: E402
```

(hapus definisi lokal `PROJECT_ROOT`/`HASIL_DIR`; `PROJECT_ROOT` di engine tidak dipakai di tempat lain dalam file — verifikasi dengan `grep -n "PROJECT_ROOT" src/core/engine.py` sebelum commit)

- [ ] **Step 4: Jalankan test baru + test engine lama yang tidak butuh model**

Run:
```bash
python3 -m pytest tests/test_engine_paths.py tests/test_wdac_patch.py -v
```
Expected: PASS semua. (Catatan: `test_engine_smoke.py` butuh model small ter-download — skip di Mac jika belum ada; akan diverifikasi in-container di Task 7.)

- [ ] **Step 5: Commit**

```bash
git add src/core/engine.py tests/test_engine_paths.py
git commit -m "refactor: engine membaca HASIL_DIR dari paths.py (DATA_DIR-aware)"
```

---