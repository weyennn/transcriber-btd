# Final Whole-Branch Review — Docker Deployment (2b85675..21135db)

## Spec Compliance

| Area | Verdict | Bukti |
|------|---------|-------|
| D-1 target btd-server | ✅ | Aditif, tidak ada yang menghalangi deploy LAN |
| D-2 single container all-in-one | ✅ | compose 1 service `transcribe`, JobManager in-process utuh |
| D-3 model small default + dropdown | ✅ | Tidak disentuh di diff; `model_default: "small"` tetap di `/api/env` |
| D-4 model via volume `./data/models` | ✅ | `HF_HOME=/data/models` (Dockerfile) + volume `./data/models:/data/models` |
| D-5 AI feature flag off | ✅ | `AI_ENABLED` default false (server.py:44), guard 503 di `/api/notulen/ai` (server.py:177-181), tombol disabled + badge "AI notulen nonaktif" di UI (app.js:40-51, fix 21135db), test `test_ai_flag.py` 3/3 |
| D-6 CPU-only | ✅ | Tidak ada CUDA/GPU dep di requirements-docker.txt; ctranslate2 int8 |
| D-7 port 8765→8080 | ✅ | compose `"8765:8080"`, EXPOSE 8080, CMD uvicorn port 8080 |
| D-8 `docker compose up -d`, build dari source | ✅ | compose `build: .`, tanpa registry/image eksternal selain base |
| D-9 WDAC patch dipertahankan | ✅ | `apply_wdac_patch()` tak disentuh (engine.py diff hanya sumber HASIL_DIR); PyAV tidak ada di requirements-docker.txt |
| D-10 GUI desktop dikeluarkan dari image | ✅ | `.dockerignore` exclude `main.py`, `src/gui/`, `src/services/`; terverifikasi 0 import runtime ke `src.services` (grep) |

## Strengths

- **Diff minimal & aditif** (273+/16−, 15 file): semua perilaku lama dipertahankan lewat fallback env — tanpa `DATA_DIR`/`CONFIG_DIR`/`AI_ENABLED`, kode berperilaku identik seperti sebelum branch ini (rollback §9 trivial: jangan set env).
- **Pertahanan berlapis D-5**: flag ditegakkan di API (503 server.py:177-181) *dan* di UI (disabled + tooltip + opacity), termasuk dua titik re-enable kode lama (`endJob`, catch handler) yang diperbaiki di fix 21135db via variabel module-level `aiEnabled`.
- **Single source of truth path**: `paths.py` satu-satunya pemilik `HASIL_DIR`/`UPLOAD_DIR`; engine (engine.py:26-27) dan server (server.py:32) sama-sama import dari sana — tidak ada duplikasi logika resolusi path.
- **Bootstrap guard tepat sasaran**: guard `DATA_DIR` di `docx_converter.py:38-39` menonaktifkan re-exec venv hanya di dalam container; perilaku Windows dev (R-13) utuh; di-backup test `test_docx_bootstrap_guard.py` yang mem-fail-kan test jika bootstrap memanggil `subprocess.call`/`sys.exit` di container.
- **TDD konsisten**: setiap task punya bukti RED (alasan gagal sesuai ekspektasi) → GREEN; total test baru 12 (paths 3, config 2, engine_paths 1, ai_flag 3, docx_guard 2, + wdac/engine regresi).
- **Dockerfile hygiene**: multi-stage (deps dipisah dari runtime), non-root `appuser`, `--no-install-recommends`, `HEALTHCHECK` ke `/healthz` dengan `start-period` 15s, `mem_limit 4g` di compose.
- **Konfigurasi env robust**: semua pembacaan env di-`.strip()` dan string kosong diperlakukan sebagai tidak diset (paths.py:19, config.py:11-12, server.py:44).

## Issues

### Critical
Tidak ada.

### Important

1. **Task 7 (build & e2e) belum dieksekusi — DoD spec §7 belum terverifikasi.** Seluruh review Docker bersifat statis: `docker build`, healthcheck in-container, e2e transcribe 75s, persistensi antar `compose down/up`, dan verifikasi browser belum pernah dijalankan (Docker daemon Mac mati sepanjang sesi; progress.md:5). Sampai ini hijau, klaim D-2/D-7/D-9 bersifat "harusnya benar", bukan "terbukti benar". Verifikasi statis sudah dilakukan (COPY paths vs struktur repo, requirements ⊆ import runtime, .dockerignore tak exclude artefak COPY), tapi itu bukan pengganti build nyata.
2. **`tests/test_web.py`: 2 failing (pre-existing side-effect Task 4).** Test lama `POST /api/notulen/ai` expect 200, padahal `AI_ENABLED` default false → 503. Perilaku baru *benar* per spec D-5, tapi suite merah. Ruling progress.md:36 menunda fix ke Task 7 (set `AI_ENABLED=true` di fixture test tersebut) — harus dieksekusi, bukan dibiarkan.
3. **Ukuran image belum diukur.** Target ~1.3–1.5 GB (task-7-brief Step 1). `requirements-docker.txt` memuat `pytest` di runtime image (karena `tests/` di-copy untuk verifikasi in-container) — dapat diterima untuk deployment internal, tapi menambah ukuran; kalau image jauh melebihi target, kandidat pertama adalah memindahkan pytest/test stage keluar dari final image.

### Minor

1. **`importlib.reload` fragility (dikenali di brief task-7):** test me-reload modul yang di-`from x import y` oleh modul lain (mis. `server.py` import `HASIL_DIR` by-name) bisa menyisakan referensi stale antar test file. Tidak terbukti flaky saat ini, tapi rapuh terhadap reordering test di masa depan. (`tests/test_ai_flag.py`, `tests/test_engine_paths.py`, `tests/test_paths.py`)
2. **PYTHONPATH manual diperlukan untuk pytest lokal** — repo tidak punya `pytest.ini`/`pyproject.toml` sehingga `pytest tests/` gagal koleksi tanpa `PYTHONPATH=.`. Pre-existing, tapi sekarang makin terasa karena jumlah test bertambah 5 file. (`repo root`, pre-existing)
3. **`test_docx_bootstrap_guard.py::test_bootstrap_guard_only_acts_on_data_dir` adalah source-string assertion** (`'os.environ.get("DATA_DIR")' in src`) — rapuh terhadap refaktor kosmetik (mis. rename ke konstanta) tanpa perubahan perilaku. (`tests/test_docx_bootstrap_guard.py:31-40`)
4. **Duplikasi kecil logika disable tombol AI** — pola `btnAINotulen.disabled = !aiEnabled` muncul di 3 lokasi (checkEnv, endJob, catch handler); helper `setAIButtonDisabled()` akan mengurangi risiko drift di masa depan. (`src/web/static/app.js:40-51, ~197, ~320`)
5. **`HEALTHCHECK` memakai `urllib` stdlib tanpa handling exit code eksplisit** — bergantung pada exception → non-zero exit, yang benar untuk python -c, tapi `curl -f` lebih idiomatik jika curl tersedia. Tidak ada bug; preferensi. (`Dockerfile:28-29`)
6. **`.dockerignore` menambah `docs/` di luar teks spec §5.3** — ruling tercatat (progress.md:19,26): docs tak dipakai runtime, image lebih kecil. Tercatat agar tidak dianggap kelalaian. (`.dockerignore:15`)

### Triage deferred minors

- **Defer ke Task 7 / follow-up:** Minor 2 (pytest.ini — satu file kecil, cocok dibarengkan saat memperbaiki test_web.py), Important 2 & 3 (memang bagian scope Task 7).
- **Defer ke backlog pasca-merge:** Minor 1 (reload fragility — refactor hanya jika test mulai flaky), Minor 3 (ubah source-string assertion jadi behavioral test), Minor 4 (helper tombol AI), Minor 5 (healthcheck curl).
- **Tidak perlu aksi:** Minor 6 (ruling .dockerignore docs/ sudah disetujui controller).

## Assessment

**Merge-ready: YA, bersyarat.** Secara kode, branch ini memenuhi D-1..D-10 tanpa temuan Critical; seluruh Important bermuara pada satu hal yang memang sudah direncanakan — **Task 7 wajib dijalankan dan hijau sebelum branch dinyatakan done** (build sukses, e2e transcribe menghasilkan `data/hasil/01_sample_75s/` di host, `/healthz` 200, AI off → 503 + tombol disabled, persistensi antar restart, dan 2 test_web.py failing diperbaiki). Karena perubahan bersifat aditif dengan fallback penuh ke perilaku lama, risiko merge ke alur kerja Windows dev existing adalah nol; satu-satunya gerbang nyata adalah verifikasi runtime Docker yang belum bisa dilakukan di mesin ini.

**Temuan: 0 Critical · 3 Important · 6 Minor.**
