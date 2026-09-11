# Report Task 5 + Task 6 + Guard Bootstrap docx_converter

Tanggal: 2026-09-11 · Branch: `docker-deployment`

## Commits

| SHA | Subject |
|---|---|
| `b520ac7` | feat: UI disable tombol AI notulen saat AI_ENABLED=false |
| `2a54801` | feat: Dockerfile multi-stage + compose + dockerignore (D-2, D-7, D-9) |
| `e8bd23b` | fix: skip venv re-exec bootstrap di dalam container (DATA_DIR guard) |

## Task 5 — Frontend disable tombol AI saat flag off

- Patch `src/web/static/app.js` blok `ai` di `checkEnv()` persis verbatim dari brief:
  - Badge: `AI <model>` (hijau) saat `ai_enabled=true`, `AI notulen nonaktif` (warn) saat false.
  - Saat `!env.ai_enabled`: `#btn-ai-notulen` → `disabled=true`, tooltip `Fitur AI notulen dimatikan di server ini (AI_ENABLED=false)`, `opacity 0.5`, `cursor not-allowed`.
- Konsistensi elemen: `btn-ai-notulen` ada di `src/web/templates/index.html:88`; konstanta `btnAINotulen` sudah didefinisikan di app.js baris 10. `/api/env` (server.py:70) mengembalikan `ai_enabled` (Task 4).
- Verifikasi JS: `node --check src/web/static/app.js` → OK.
- Verifikasi manual browser (AI_ENABLED false/true) **DITUNDA ke Task 7** — server lokal butuh model whisper; sesuai brief Step 2.

## Task 6 — Artefak Docker

File dibuat persis verbatim dari brief/spec §5.1–5.3:
- `requirements-docker.txt` — fastapi, uvicorn, python-multipart, faster-whisper, ctranslate2, huggingface_hub, python-docx, httpx, pytest.
- `Dockerfile` — multi-stage (deps → runtime), ffmpeg, user `appuser`, ENV `DATA_DIR`/`CONFIG_DIR`/`AI_ENABLED`/`HF_HOME`/`PORT`/`PYTHONUNBUFFERED`, healthcheck `/healthz`, CMD uvicorn `src.web.server:app` port 8080.
- `docker-compose.yml` — port 8765:8080, 4 volume data, `AI_ENABLED: "false"`, mem_limit 4g.
- `.dockerignore` — persis spec §5.3.

### Verifikasi statis (Docker daemon Mac mati — build TIDAK dicoba)

1. **COPY paths vs struktur repo**: `COPY requirements-docker.txt` ✓ (root), `COPY src/` ✓ (ada), `COPY tests/` ✓ (ada).
2. **requirements-docker.txt ⊆ kebutuhan src/**: import pihak ketiga di `src/` (non-gui/services) = `fastapi`, `httpx`, `docx` (python-docx), `faster_whisper`, `huggingface_hub`, `numpy`(dep faster-whisper), `uvicorn`, `python-multipart` (upload form) — semua tercakup. `pytest` ikut karena `tests/` di-copy.
3. **.dockerignore tidak meng-exclude artefak COPY**: `src/gui/` & `src/services/` di-ignore tapi itu subpath — `src/web`, `src/core`, `src/export`, `src/notulen`, `src/utils` tetap masuk; `tests/baseline_output/` di-ignore, sisa `tests/` masuk; `requirements-docker.txt` & `Dockerfile` tidak kena ignore. ✓
4. **docker-compose.yml** lolos lint YAML.

### DITUNDA ke Task 7 (butuh Docker daemon)
- `docker build` & e2e container (healthcheck, volume, AI_ENABLED on/off, verifikasi browser Task 5).

## Guard bootstrap docx_converter (ruling controller)

- `src/export/docx_converter.py::_rerun_with_venv_python()`: guard `if os.environ.get("DATA_DIR"): return` paling atas. Dockerfile menyet `DATA_DIR=/data` → di container tidak ada re-exec/hang; Windows dev tidak terpengaruh (DATA_DIR tidak diset).
- Fix ini juga menyembuhkan **PermissionError di Mac dev**: sebelumnya `tests/test_web.py` gagal collection (`Operation not permitted: .venv/Scripts/python.exe`); sesudah patch (dengan `DATA_DIR` di env test) collection berhasil.
- Test baru `tests/test_docx_bootstrap_guard.py` — **2 passed**: (1) DATA_DIR=/data → import ulang modul tanpa SystemExit/subprocess; (2) guard string ada di source.

## Hasil test suite

- `tests/test_docx_bootstrap_guard.py`: 2 passed.
- `tests/test_ai_flag.py`, `tests/test_paths.py`, `tests/test_engine_paths.py`: passed (dengan DATA_DIR diset).
- `tests/test_web.py`: 7 passed, 2 failed — **pre-existing, bukan regresi patch ini** (503 AI-disabled di test notulen AI yang expect 200; terkait perubahan Task 4 `AI_ENABLED` default false, di luar scope task ini). Tanpa `DATA_DIR`, test_web tetap PermissionError saat collection karena bootstrap tetap aktif di dev — perilaku by-design di luar container.

## Concerns

1. `test_web.py` 2 failing (Task 4 side-effect, AI_ENABLED default false vs test lama yang expect endpoint AI 200) — perlu diputuskan apakah test diupdate (Task 7/owner Task 4).
2. Docker build & e2e belum terverifikasi sama sekali (daemon mati) — wajib Task 7.
3. `.dockerignore` mengabaikan `src/services/` — dipastikan tidak ada import runtime web ke `src.services`; kalau nanti ada, build runtime akan ImportError.

## Fix Round 1/5 — Review Task 5 (tombol AI re-enable sendiri)

**Commit:** 21135db fix: tombol AI tetap disabled saat AI_ENABLED=false setelah job selesai

### Yang diubah (src/web/static/app.js)
1. Tambah `let aiEnabled = true;` di bawah `let aiRunning` (baris 25).
2. `checkEnv()`: set `aiEnabled = !!env.ai_enabled;` lalu blok disable memakai `if (!aiEnabled)`.
3. `endJob()` (~baris 197): `btnAINotulen.disabled = false;` → `btnAINotulen.disabled = !aiEnabled;`
4. Catch handler notulen (~baris 320): pola sama, `disabled = !aiEnabled`.
5. Grep `btnAINotulen`: tidak ada lokasi lain yang enable tombol tanpa cek flag (hanya deklarasi, disable di checkEnv/click handler, dan dua titik yang sudah diperbaiki).

### Verifikasi
```
$ node --check src/web/static/app.js
SYNTAX OK
```

### Logika
`checkEnv()` mengisi `aiEnabled` dari `/api/env`; semua enable/disable tombol AI kini menghormati flag tersebut, sehingga tombol tetap disabled saat `AI_ENABLED=false` meski job transkripsi selesai atau job notulen gagal.
