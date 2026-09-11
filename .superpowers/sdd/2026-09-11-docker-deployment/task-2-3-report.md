# Report Task 2 & 3 — Docker Deployment

**Branch:** `docker-deployment` · **Executor:** Hermes agent (solo, tanpa subagent)
**Metodologi:** TDD per task (RED → verifikasi gagal → implementasi → GREEN)

---

## Task 2: `config.py` — CONFIG_DIR override

### Implementasi
`src/utils/config.py:11-20` — `_CONFIG_DIR` sekarang membaca env `CONFIG_DIR` terlebih dahulu
(di-`strip()`, string kosong diabaikan); jika tidak diset, perilaku lama dipertahankan
(platformdirs `user_config_dir("TranscribeGUI")`, fallback `~/.transcribe_gui`).
Docstring modul ditambah: "Di container Docker: env `CONFIG_DIR` (→ /data/config) menimpa lokasi default."
Signature `config_path() / load_config() / save_config()` tidak berubah.

### Bukti TDD
**RED** — `pytest tests/test_config.py -v`:
```
FAILED tests/test_config.py::test_config_dir_override - AssertionError:
  assert PosixPath('/Users/wayeien/Library/Application Support/TranscribeGUI/config.json')
      == tmp_path / 'config.json'
1 failed, 4 passed
```
Gagal dengan alasan yang diharapkan: config masih pakai platformdirs, mengabaikan env CONFIG_DIR.

**GREEN** — `pytest tests/test_config.py -v`:
```
tests/test_config.py::test_config_dir_override PASSED
tests/test_config.py::test_tanpa_env_fallback PASSED
2 passed in 0.04s
```

### Files changed
- `src/utils/config.py` (modified)
- `tests/test_config.py` (baru)

### Commit
`430b2bb feat: CONFIG_DIR env override untuk settings persistence` (pesan persis sesuai brief)

### Self-review
- Kode patch verbatim dari brief (Step 3), termasuk `noqa: BLE001` dan docstring.
- `test_tanpa_env_fallback` tidak menyentuh disk — hanya assertion pada path.
- LSP warning "platformdirs could not be resolved" adalah pre-existing (import opsional di dalam try/except; platformdirs ada di runtime interpreter pyenv, tidak terdaftar di environment statis Pyright).

---

## Task 3: `engine.py` — HASIL_DIR dari paths.py

### Implementasi
`src/core/engine.py:26-27` — definisi lokal `PROJECT_ROOT`/`HASIL_DIR` dihapus, diganti:
```python
# Root state: dari paths.py (menghormati env DATA_DIR di Docker)
from src.utils.paths import HASIL_DIR  # noqa: E402
```
`engine.HASIL_DIR` tetap ada sebagai alias module-level, nilainya = `paths.HASIL_DIR` (satu sumber kebenaran).

### Verifikasi PROJECT_ROOT (instruksi controller)
```
$ grep -n "PROJECT_ROOT" src/core/engine.py
27:PROJECT_ROOT = Path(__file__).resolve().parents[2]
28:HASIL_DIR = PROJECT_ROOT / "transcribe_hasil"
```
Hanya 2 pemakaian — definisi itu sendiri. Tidak ada pemakaian lain, jadi `PROJECT_ROOT` aman dihapus.

### Bukti TDD
**RED** — `pytest tests/test_engine_paths.py -v`:
```
FAILED tests/test_engine_paths.py::test_engine_hormati_data_dir - AssertionError:
  assert '/Users/wayeien/Documents/firmware_transcribe/transcribe_hasil' == '/data/hasil'
1 failed
```
Gagal dengan alasan yang diharapkan: engine.HASIL_DIR masih `<project>/transcribe_hasil`.

**GREEN** — `pytest tests/test_engine_paths.py tests/test_wdac_patch.py -v`:
```
tests/test_engine_paths.py::test_engine_hormati_data_dir PASSED
tests/test_wdac_patch.py::test_no_real_av_loaded PASSED
tests/test_wdac_patch.py::test_patch_idempotent PASSED
tests/test_wdac_patch.py::test_engine_import_does_not_load_faster_whisper PASSED
tests/test_wdac_patch.py::test_fake_av_registered FAILED (pre-existing, lihat Concerns)
```

**Regression check** — 16 passed, 1 failed (pre-existing) di seluruh test yang dapat dikoleksi:
`test_engine_paths + test_config + test_paths + test_output_writer + test_anti_hallucination + test_wdac_patch`.

### Files changed
- `src/core/engine.py` (modified)
- `tests/test_engine_paths.py` (baru)

### Commit
`22c40e9 refactor: engine membaca HASIL_DIR dari paths.py (DATA_DIR-aware)` (pesan persis sesuai brief)

### Self-review
- Patch verbatim dari brief (Step 3). Import ditempatkan di posisi baris yang sama (setelah class `CancelledError`), dengan `noqa: E402` karena bukan di top-of-file.
- Tidak ada perubahan signature method apapun.
- `test_engine_smoke.py` di-skip sesuai catatan brief (butuh model small; diverifikasi in-container di Task 7).

---

## Concerns (berlaku untuk kedua task)

1. **Pre-existing failure — bukan regresi:** `tests/test_wdac_patch.py::test_fake_av_registered` gagal
   dengan `ModuleNotFoundError: No module named 'faster_whisper'` di environment Mac ini.
   Diverifikasi via `git stash` (kode sebelum perubahan saya) → gagal identik. `faster_whisper`
   memang tidak terinstall di interpreter pyenv lokal; akan PASS in-container (Dockerfile menginstall
   requirements). Tidak terkait Task 2/3.
2. **PYTHONPATH diperlukan:** pytest tidak mengimpor `src.*` tanpa `PYTHONPATH=.` (repo tidak punya
   pytest.ini/pyproject config; berlaku juga untuk test_paths.py dari Task 1 — bukan masalah baru).
   Di Docker, WORKDIR + `python -m pytest` dari root mengatasi ini.
3. **Test tak terkoleksi (pre-existing, env Mac):** `tests/test_web.py` error saat collection dan
   `tests/test_ai_generator.py` `PermissionError` — keduanya pre-existing, tidak disentuh task ini.
4. `.venv` di repo berformat Windows (Scripts/, bukan bin/) sehingga test dijalankan via pytest
   pyenv system — dependency yang tersedia di sana cukup untuk semua test baru.
