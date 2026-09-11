# Task 7 Prep Report — Paket Verifikasi Server-Side btd-server

Tanggal: 2026-09-11 · Dikerjakan: manual (tanpa subagent, tanpa menjalankan docker)

## Deliverable & Commit

| # | Deliverable | Commit SHA | Subject |
|---|---|---|---|
| 1 | Fix tests/test_web.py (AI_ENABLED=true) | `2ae6c4f` | test: test_web notulen AI set AI_ENABLED=true mengikuti feature flag D-5 |
| 2 | verify_deploy.sh (executable, mode 100755) | `290aa36` | feat: verify_deploy.sh — verifikasi otomatis DoD spec §7 untuk btd-server |
| 3 | DEPLOY.md | `8f5f941` | docs: DEPLOY.md — runbook btd-server |

## 1. Fix tests/test_web.py

**Temuan:** commit `2ae6c4f` sudah ada di HEAD sesi sebelumnya (diff +3 baris), maka tidak dibuat commit baru.

**Implementasi aktual** (baris 10–11 `tests/test_web.py`):
```python
os.environ.setdefault("AI_ENABLED", "true")
```
ditempatkan sebelum `from src.web.server import app`.

**Penyimpangan dari brief (disengaja, fungsional setara):** brief meminta pattern
`monkeypatch.setenv` + `importlib.reload(server)` seperti `tests/test_ai_flag.py`.
Pattern tersebut tidak bisa dipakai di `test_web.py` karena:
1. `client = TestClient(app)` dibuat **module-level** dan dipakai 9 test; reload
   per-test akan memaksa refactor ke fixture client — mengubah perilaku/struktur
   test lain (dilarang brief: "JANGAN mengubah perilaku test lain").
2. `importlib.reload(server)` di tengah file tidak meng-update referensi `app`
   yang sudah dipegang `TestClient`, dan berisiko stale-import (catatan risiko
   yang sama tercatat di `task-7-brief.md` self-review log).

`os.environ.setdefault` membaca titik yang sama (`server.py:44` membaca env saat
import), tidak menimpa env eksplisit user, dan tidak menyentuh test lain.

## Verifikasi

### pytest tests/test_web.py
Perintah brief apa adanya (`PYTHONPATH=. .venv-test/bin/python -m pytest tests/test_web.py -q`)
**gagal saat collection** — bukan karena perubahan ini:

```
PermissionError: [Errno 1] Operation not permitted: '/Users/.../.venv/Scripts/python.exe'
```
Penyebab: bootstrap re-exec di `src/export/docx_converter.py` (pre-existing,
ditujukan untuk Windows; path `.venv/Scripts/python.exe` adalah venv Windows yang
tidak bisa dieksekusi di macOS). Guard `DATA_DIR` dari commit `e8bd23b` menonaktifkan
bootstrap ini, jadi verifikasi dijalankan dengan `DATA_DIR` diset (sama seperti
kondisi di dalam container, di mana Dockerfile meng-set `DATA_DIR=/data`):

```
DATA_DIR=/tmp/mt-test PYTHONPATH=. .venv-test/bin/python -m pytest tests/test_web.py -q
→ 9 passed, 2 warnings in 11.42s
```

Dua test target secara spesifik:
```
tests/test_web.py::test_notulen_ai_endpoint            PASS
tests/test_web.py::test_notulen_ai_rejects_outside_folder PASS  (0.31s)
```
Tidak ada fail/skip — termasuk `test_upload_and_transcribe_sse` (transcribe asli
model small, PASS karena model ter-cache di host dev). Warning hanya deprecation
Starlette (pre-existing).

### bash -n verify_deploy.sh
`SYNTAX OK` (exit 0). `shellcheck` tidak tersedia di mesin ini.
Script di-chmod +x dan ter-commit dengan mode `100755`.

### Pembacaan ulang logika verify_deploy.sh (line-by-line)
- `set -euo pipefail`, `cd` ke root repo, helper `pass`/`gagal` (gagal → pesan jelas + exit 1).
- Idempotent: `docker compose down` di awal (`|| true`), **tidak** menyentuh `data/`.
- Deteksi `docker compose` plugin vs `docker-compose` legacy.
- Langkah 2 menjalankan 6 file test termasuk `tests/test_docx_bootstrap_guard.py` (diverifikasi file ada).
- Langkah 4 parse `/api/env` via `python3` heredoc (bukan jq): assert `ffmpeg.ok is True`, `ai_enabled is False`, `output_dir == "/data/hasil"`.
- Langkah 5: path upload diambil dari JSON response (bukan hardcode `/data/uploads/...`); poll status tiap 10 dtk maks 1800 dtk; status terminal yang diterima `done`/`finished` (status aktual server adalah `"done"` — diverifikasi di `src/web/job_manager.py:138`); folder hasil dicari via `ls -dt data/hasil/*_sample_75s*/` terbaru (tidak hardcode `01_`); assert `transkrip.txt` + `transkrip.json` ada di host.
- Langkah 6: `curl -s -o file -w "%{http_code}"`, assert code `503` + `grep -q "dimatikan"` pada body.
- Langkah 7: down → up → tunggu healthy → assert history mengandung `sample_75s` (python3) + `data/config/config.json` ada di host.
- Akhir: "SEMUA VERIFIKASI LULUS (7/7 langkah)" + petunjuk stop/pakai.
- **Tidak ada perintah docker yang dijalankan di mesin ini** (sesuai kontrak).

### DEPLOY.md
Mencakup semua poin brief: prasyarat (compose plugin, port 8765, internet sekali),
quick start (verify_deploy.sh atau compose up manual), tabel 8 env var (DATA_DIR,
CONFIG_DIR, AI_ENABLED, HF_HOME, PORT, TRANSCRIBE_AI_BASE_URL/MODEL/API_KEY),
aktivasi AI (edit compose + `up -d --force-recreate`), operasional (logs/down/
update via `git pull && up -d --build`/bersih-bersih `data/uploads`), catatan
(model di `data/models`, mem_limit 4GB, tanpa GPU).

## Concerns / Risiko untuk eksekusi di btd-server

1. **Bootstrap docx_converter** (di atas): di dalam container aman karena Dockerfile
   meng-set `DATA_DIR=/data`. Jika user menjalankan pytest di luar Docker tanpa
   `DATA_DIR`, collection error akan muncul lagi — ini pre-existing, bukan regresi.
2. **Ukuran image**: target spec ~1.3–1.5GB belum terverifikasi (build hanya bisa
   di btd-server); script mencetak ukuran aktual di langkah 1.
3. **Langkah 5 pertama kali**: download model ~460MB — durasi tergantung bandwidth;
   timeout 30 menit sesuai brief.
4. **Upload idempotency**: server menambah suffix `-2` pada nama file upload duplikat,
   sehingga run kedua menghasilkan folder `XX_sample_75s-2` — pattern glob
   `*_sample_75s*/` di langkah 5 sudah mengakomodasi ini.
5. Brief menyebut "test lain yang butuh model whisper/9router boleh fail/skip" —
   aktualnya **semua 9 test PASS** di environment ini, jadi tidak ada yang perlu
   dicatat sebagai pre-existing failure.
