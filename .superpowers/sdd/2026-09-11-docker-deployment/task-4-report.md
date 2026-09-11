# Task 4 Report — server.py: UPLOAD_DIR dari paths + AI_ENABLED flag + /healthz

**Status:** SELESAI (GREEN)
**Commit:** `2e9c7f1` — `feat: AI_ENABLED feature flag + UPLOAD_DIR dari paths + /healthz`

## Lingkup

| File | Perubahan |
|------|-----------|
| `src/web/server.py` | `UPLOAD_DIR` di-import dari `src.utils.paths` (DATA_DIR-aware, `PROJECT_ROOT` lokal dihapus); module-level `AI_ENABLED` (default `false`); key `ai_enabled` di response `/api/env`; guard 503 di atas `POST /api/notulen/ai`; endpoint baru `GET /healthz` → `{"ok": true}` |
| `tests/test_ai_flag.py` | Baru — 3 test (env off/on expose flag; 503 saat off) |

## TDD Evidence

Interpreter test: `PYTHONPATH=. .venv-test/bin/python -m pytest ...` (`.venv-test` dari Task 1; PYTHONPATH=`. ` diperlukan karena repo tak punya pytest.ini — dikenal dari report Task 2-3).

### Setup venv-test (prasyarat, sekali jalan)
`.venv-test` Task 1 stdlib-only. Test ini butuh import `src.web.server` penuh, jadi diinstall ke `.venv-test`:
`fastapi`, `httpx`, `python-multipart`, `python-docx`, `huggingface_hub`, `numpy`, `faster-whisper`.
`.venv-test/` di-gitignore; tidak ada perubahan repo.

### Workaround bootstrap docx_converter (macOS lokal saja)
`src/export/docx_converter.py` (diimpor via `ai_generator`) punya bootstrap module-level yang re-exec ke `.venv/Scripts/python.exe` (Windows venv, ada di folder kerja lokal tapi di-gitignore & tidak ada di Docker). Di macOS re-exec ini gagal `PermissionError`, jadi test dijalankan dengan `.venv` di-rename sementara (`mv .venv .venv-win-off`) agar bootstrap fallback ke python saat ini. Setelah test selesai `.venv` dikembalikan. Tidak ada perubahan kode produksi. Task 6 (Dockerfile) akan menangani ini secara definitif.

### RED (sebelum implementasi)
Command: `PYTHONPATH=. .venv-test/bin/python -m pytest tests/test_ai_flag.py -v`
```
tests/test_ai_flag.py::test_env_expose_ai_enabled_off FAILED  — KeyError: 'ai_enabled'
tests/test_ai_flag.py::test_env_expose_ai_enabled_on  FAILED  — KeyError: 'ai_enabled'
tests/test_ai_flag.py::test_notulen_ai_503_saat_off   FAILED  — assert 404 == 503
======================== 3 failed =========================
```
Persis sesuai ekspektasi brief (KeyError 'ai_enabled'; status 404 bukan 503).

### GREEN (setelah implementasi)
Command: `PYTHONPATH=. .venv-test/bin/python -m pytest tests/test_ai_flag.py -v`
```
tests/test_ai_flag.py::test_env_expose_ai_enabled_off PASSED
tests/test_ai_flag.py::test_env_expose_ai_enabled_on PASSED
tests/test_ai_flag.py::test_notulen_ai_503_saat_off PASSED
======================== 3 passed, 2 warnings in 0.54s =========================
```
(2 warnings = DeprecationWarning starlette/httpx, bukan dari kode ini.)

### Regresi
Command: `PYTHONPATH=. .venv-test/bin/python -m pytest tests/test_paths.py tests/test_config.py tests/test_engine_paths.py -v`
```
6 passed in 0.02s
```

### Verifikasi manual `/healthz` + default flag
```python
TestClient(server.app).get('/healthz')  → 200 {'ok': True}
server.AI_ENABLED                       → False   # default tanpa env
GET /api/env → json()['ai_enabled']     → False   # default
```

## Interface yang dihasilkan (untuk Task 5)
- `server.AI_ENABLED: bool` module-level, dibaca dari env `AI_ENABLED` (case-insensitive, trim), default `false`.
- `GET /api/env` → response memuat `ai_enabled: bool`.
- `POST /api/notulen/ai` → saat off: HTTP 503 `{"detail": "Fitur AI notulen dimatikan di server ini (AI_ENABLED=false)"}` (guard di atas, sebelum validasi body); saat on: perilaku lama.
- `GET /healthz` → `200 {"ok": true}` (untuk Docker HEALTHCHECK, Task 6/7).

## Concerns
1. **Bootstrap `docx_converter.py` Windows-only**: re-exec ke `.venv/Scripts/python.exe` saat sys.prefix ≠ `<project>/.venv`. Di Docker `.venv` tak ada (Dockerfile install ke sistem → fallback no-op, aman), tapi di dev macOS/Linux dengan `.venv` Windows ter-copy akan PermissionError. Perlu dibetulkan di Task 6/7 (atau task terpisah).
2. `test_web.py` existing tidak dijalankan (butuh model whisper cache + ffmpeg + 9router; di luar scope, sama seperti Task sebelumnya).
3. `.venv-test` kini berisi deps penuh server (faster-whisper dsb.) — hanya untuk test lokal; gitignored.
