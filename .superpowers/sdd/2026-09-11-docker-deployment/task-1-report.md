# Task 1 Report: DATA_DIR override di src/utils/paths.py (termasuk Task 0)

## Ringkasan
- Task 0: `.gitignore` dibuat (verbatim dari brief + `.venv-test/` per controller), `git init`, baseline commit di branch default (`master`), lalu branch kerja `docker-deployment` dibuat (`git checkout -b docker-deployment`).
- Task 1: `src/utils/paths.py` kini mengekspor `HASIL_DIR: Path` dan `UPLOAD_DIR: Path` yang menghormati env `DATA_DIR` (fallback perilaku lama jika env kosong/tidak diset). Fungsi `project_root()`, `stem()`, `auto_folder()`, `list_history()` tidak disentuh.

## Commits
| SHA | Subject | Branch |
|---|---|---|
| `2b85675` | chore: baseline sebelum dockerization | master (dibuat sebelum branch kerja) |
| `7da4967` | feat: DATA_DIR env override untuk HASIL_DIR/UPLOAD_DIR | docker-deployment |

## Files Changed
- Create: `.gitignore` (konten brief + `.venv-test/`)
- Modify: `src/utils/paths.py` (header/docstring + blok DATA_DIR; sisa file identik)
- Create: `tests/test_paths.py` (verbatim dari brief)

## Bukti TDD

### Setup runner
Repo hanya punya `.venv` Windows (`Scripts/python.exe`) — tidak bisa jalan di Mac. Dibuat `.venv-test` (Python 3.12.1, pytest 9.1.1, stdlib-only untuk test ini). `.venv-test/` masuk `.gitignore` per instruksi controller.

### RED — Step 2 (sebelum implementasi)
Command: `.venv-test/bin/python -m pytest tests/test_paths.py -v`

```
tests/test_paths.py::test_default_tanpa_env FAILED                       [ 33%]
tests/test_paths.py::test_data_dir_override FAILED                       [ 66%]
tests/test_paths.py::test_env_kosong_diabaikan PASSED                    [100%]

E       AttributeError: module 'src.utils.paths' has no attribute 'UPLOAD_DIR'
tests/test_paths.py:20: AttributeError

E       AssertionError: assert '/Users/wayei...nscribe_hasil' == '/data/hasil'
tests/test_paths.py:25: AssertionError
========================= 2 failed, 1 passed in 0.02s ==========================
```
Verdict RED valid: gagal karena fitur belum ada (`UPLOAD_DIR` belum diekspor, `DATA_DIR` belum dibaca), persis ekspektasi brief. `test_env_kosong_diabaikan` pass dini karena perilaku lama == fallback — expected, assertion-nya hanya memeriksa fallback.

### GREEN — Step 4 (setelah implementasi verbatim dari brief)
Command: `.venv-test/bin/python -m pytest tests/test_paths.py -v`

```
tests/test_paths.py::test_default_tanpa_env PASSED                       [ 33%]
tests/test_paths.py::test_data_dir_override PASSED                       [ 66%]
tests/test_paths.py::test_env_kosong_diabaikan PASSED                    [100%]

============================== 3 passed in 0.01s ===============================
```
Output pristine, tanpa warning.

## Implementasi (diff inti `src/utils/paths.py`)
```python
_DATA_DIR = os.environ.get("DATA_DIR", "").strip()
if _DATA_DIR:
    HASIL_DIR = Path(_DATA_DIR) / "hasil"
    UPLOAD_DIR = Path(_DATA_DIR) / "uploads"
else:
    HASIL_DIR = PROJECT_ROOT / "transcribe_hasil"
    UPLOAD_DIR = PROJECT_ROOT / "uploads"
```

## Interface yang diproduksi (untuk task berikut)
- `src.utils.paths.HASIL_DIR: Path` — `DATA_DIR/hasil` jika env diset, else `PROJECT_ROOT/transcribe_hasil`
- `src.utils.paths.UPLOAD_DIR: Path` — `DATA_DIR/uploads` jika env diset, else `PROJECT_ROOT/uploads`
- `PROJECT_ROOT` tetap diekspor; `project_root()`, `stem()`, `auto_folder()`, `list_history()` tidak berubah.

## Self-review
- [x] Test ditulis sebelum kode produksi; RED disaksikan dengan alasan yang benar.
- [x] Implementasi verbatim dari brief (`.strip()` menangani env berisi whitespace).
- [x] Tidak ada perubahan pada fungsi existing — diff hanya header + blok kondisional.
- [x] Pesan commit persis seperti brief.
- [x] Working tree bersih setelah commit; `.venv-test/` ter-ignore.
- [x] Nilai `HASIL_DIR`/`UPLOAD_DIR` dievaluasi saat import — test me-reload module; konsisten dengan pola consumer yang import sekali saat startup (Docker env sudah ada sebelum proses jalan).

## Concerns
1. Test suite pre-existing (`tests/test_engine_smoke.py`, dll.) tidak dijalankan — butuh deps berat (faster-whisper, dll.) yang tidak tersedia di Mac venv; di luar scope brief yang menyatakan "test ini murni stdlib". Risiko regresi pada fungsi yang tidak diubah dianggap nol (diff tidak menyentuh mereka).
2. `.venv` Windows lama tetap ter-commit? Tidak — `.gitignore` mengecualikannya sejak baseline, jadi tidak masuk repo.
