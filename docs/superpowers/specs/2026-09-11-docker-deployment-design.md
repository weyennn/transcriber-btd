# PRD & Desain Arsitektur — Mesin Transcribe Docker Deployment

> **Tanggal:** 2026-09-11
> **Status:** Disetujui user (siap implementation plan)
> **Scope:** Rekonstruksi `firmware_transcribe` menjadi app Docker yang deployable ke **btd-server**
> **Dokumen acuan:** `README_GUI.md` (risk register R-01..R-15, W-01..W-04, AI-01..AI-03, P3-01)

---

## 1. Latar Belakang & Tujuan

Mesin Transcribe saat ini berjalan sebagai aplikasi lokal (Windows, venv) dengan
dashboard web FastAPI + SSE. Deployment ke btd-server membutuhkan packaging
ulang sebagai container Docker agar:

- Dapat di-deploy & di-restart deterministik (`docker compose up -d`)
- Dependensi (ffmpeg, Python, libs) terkunci dalam image — tidak tergantung kondisi host
- State (model whisper, uploads, hasil, config) persisten di host via volume
- Perilaku user-facing **tidak berubah** (dashboard, flow upload → transcribe → hasil)

### Non-Goals (out of scope)

- Multi-user, login/auth, riwayat per user
- Multi-container architecture (worker terpisah, Redis queue)
- GPU support
- Packaging desktop (Phase 4 PyInstaller — tetap ditunda)
- Registry/CI pipeline (deploy langsung build di/dikirim ke server)

---

## 2. Keputusan Desain (dari sesi brainstorming 2026-09-11)

| # | Keputusan | Pilihan | Alasan |
|---|-----------|---------|--------|
| D-1 | Target deploy | btd-server (internal, LAN kantor) | Sesuai permintaan user |
| D-2 | Arsitektur | **Single container all-in-one** (Opsi A) | Single-user antre job; JobManager in-process sudah mendukung; nol komponen tambahan |
| D-3 | Model whisper | Default `small` (int8, CPU), dropdown tiny/base/small/medium tetap aktif | Pertahankan perilaku existing; `small` teruji stress test 1j42m stabil ~520 MB RSS |
| D-4 | Distribusi model | Volume `./data/models` (HF cache), download sekali saat first run | Server punya internet; image tetap ramping; model persisten antar restart |
| D-5 | AI notulen | **Feature flag `AI_ENABLED=false`** (default off); kode `ai_generator.py` dipertahankan | 9router belum tentu ada di server; bisa dinyalakan via env tanpa rebuild |
| D-6 | Compute | CPU-only | Sesuai keputusan user; ctranslate2 int8 |
| D-7 | Port host | **8765** (seperti sekarang) → container 8080 | Kebiasaan user; W-01 (port bentrok) terselesaikan oleh port mapping Docker |
| D-8 | Deploy | `docker compose up -d`, build dari source, tanpa registry | Sesuai keputusan user |
| D-9 | WDAC patch | **Dipertahankan** | Di Linux patch ini berfungsi "decode audio via ffmpeg (bukan PyAV)" → PyAV tidak perlu ada di image, Dockerfile lebih sederhana |
| D-10 | GUI desktop | PySide6/`src/gui`/`src/services`/`main.py` **dikeluarkan dari image** | Arsip PoC; memangkas ukuran image & attack surface |

---

## 3. Arsitektur

### 3.1 Diagram

```
btd-server (Linux + Docker)
│
├── docker-compose.yml            # 1 service: transcribe
├── Dockerfile                    # multi-stage, python:3.12-slim + ffmpeg
├── .dockerignore
├── requirements-docker.txt
│
├── data/                         # STATE PERSISTEN (host, bukan di image)
│   ├── models/                   # HF cache → $HF_HOME (model download sekali)
│   ├── uploads/                  # audio dari browser
│   ├── hasil/                    # transcribe_hasil/XX_nama/ (txt+json+docx)
│   └── config/                   # settings.json (pilihan model/bahasa terakhir)
│
└── src/                          # kode existing (minus gui/, services/, main.py)
    ├── core/                     # engine, audio_decoder, merger, writer  [tidak disentuh]
    ├── web/                      # server, job_manager, templates, static [server.py di-patch]
    ├── notulen/                  # ai_generator (feature-flagged), generator
    ├── export/                   # docx_converter                          [tidak disentuh]
    └── utils/                    # paths, config, ffmpeg_checker           [di-patch DATA_DIR]

┌────────────────────────── container: mesin-transcribe ──────────────────────────┐
│  uvicorn → FastAPI :8080                                                        │
│    ├─ dashboard web (templates/index.html + static)                             │
│    ├─ JobManager: 1 job berjalan, antre, background thread, SSE real-time       │
│    ├─ faster-whisper small/int8 (CPU) — model dari /data/models                 │
│    └─ AI notulen: 503 "dimatikan" jika AI_ENABLED=false                         │
│  volumes: /data/models, /data/uploads, /data/hasil, /data/config                │
│  port map: host 8765 → container 8080                                           │
│  memory limit: 4G · restart: unless-stopped · healthcheck /api/env              │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow (identik dengan existing)

```
Browser ──POST /api/upload────▶ /data/uploads/<nama>.mp3
        ──POST /api/transcribe▶ JobManager → thread worker
                                    │ faster-whisper (small/int8/CPU)
                                    │ model cache: /data/models (HF_HOME)
                                    ▼
        ◀──SSE /api/jobs/{id}/stream── log, progress, segmen real-time
                                    ▼
                        /data/hasil/01_<nama>/transkrip.{txt,json}
Browser ──GET /api/history────▶ daftar hasil lama
        ──POST /api/notulen/ai─▶ 503 {detail: "Fitur AI dimatikan"}  [AI_ENABLED=false]
```

---

## 4. Perubahan Kode (minimal, logika existing dipertahankan)

| File | Perubahan | Catatan |
|------|-----------|---------|
| `src/utils/paths.py` | Root path dibaca dari env `DATA_DIR` (default `/data`); fallback ke perilaku lama (relatif project root) jika env tidak diset | Windows dev tetap jalan tanpa perubahan. **Catatan:** `engine.py` mendefinisikan `PROJECT_ROOT`/`HASIL_DIR` sendiri — disatukan agar membaca dari `paths.py` (satu sumber kebenaran), perilaku identik |
| `src/utils/config.py` | **Prioritas path config:** (1) env `CONFIG_DIR` (di container → `/data/config`); (2) perilaku existing (platformdirs / `~/.transcribe_gui`) jika env tidak diset. Perilaku load/backup `.bak` (R-12) tidak berubah | Di container, `Path.home()` milik `appuser` ikut terhapus saat container dibuang → config wajib diarahkan ke volume agar persistence (kriteria verifikasi #5) benar-benar terpenuhi |
| `src/web/server.py` | (a) `AI_ENABLED = os.environ.get("AI_ENABLED","false").lower()=="true"`; (b) `/api/env` expose `ai_enabled`; (c) `POST /api/notulen/ai` → 503 jika off; (d) port default uvicorn 8080 via env `PORT` | Launcher `transcribe` lama tidak disentuh |
| `src/web/templates/index.html` + `static/app.js` | Tombol "🤖 Buat Notulen AI" disabled + tooltip "Fitur AI dimatikan di server ini" saat `/api/env.ai_enabled == false` | Satu-satunya perubahan UI |
| `requirements-docker.txt` | **Baru:** fastapi, uvicorn, python-multipart, faster-whisper, ctranslate2, huggingface_hub, python-docx, httpx, pytest. **Tanpa:** PySide6, pyinstaller, onnxruntime, numpy eksplisit | Subset requirements_gui.txt; pytest disertakan agar verifikasi #2 (test in-container) bisa jalan |
| `Dockerfile`, `docker-compose.yml`, `.dockerignore` | **Baru** | Lihat §5 |
| `src/core/engine.py` | **Tidak disentuh** | WDAC patch dipertahankan (D-9) |
| `src/web/job_manager.py` | **Tidak disentuh** | Antre job + SSE sudah sesuai kebutuhan |
| `tests/` | **Tidak disentuh**; dijalankan di dalam container saat verifikasi | Terutama `test_wdac_patch.py`, `test_engine_smoke.py` |

**Catatan env var baru/aktf:**

| Env var | Default | Fungsi |
|---------|---------|--------|
| `DATA_DIR` | `/data` (di container) | Root state: uploads, hasil |
| `CONFIG_DIR` | `/data/config` (di container) | Lokasi `config.json` settings (fallback: platformdirs/`~/.transcribe_gui` di luar container) |
| `AI_ENABLED` | `false` | Feature flag notulen AI |
| `HF_HOME` | `/data/models` | Lokasi cache HuggingFace (model whisper) |
| `PORT` | `8080` | Port uvicorn di dalam container |
| `TRANSCRIBE_AI_BASE_URL` | — (existing) | Dipakai hanya jika `AI_ENABLED=true` |
| `TRANSCRIBE_AI_MODEL` / `TRANSCRIBE_AI_API_KEY` | — (existing) | Dipakai hanya jika `AI_ENABLED=true` |

---

## 5. Artefak Deployment

### 5.1 Dockerfile (multi-stage)

```dockerfile
# ── Stage 1: install deps ──
FROM python:3.12-slim AS deps
WORKDIR /app
COPY requirements-docker.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-docker.txt

# ── Stage 2: runtime ──
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*
COPY --from=deps /install /usr/local
WORKDIR /app
COPY src/ ./src/

RUN useradd -m appuser && mkdir -p /data && chown appuser:appuser /data
USER appuser

ENV DATA_DIR=/data \
    AI_ENABLED=false \
    HF_HOME=/data/models \
    PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8080/api/env')"
CMD ["python", "-m", "uvicorn", "src.web.server:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 5.2 docker-compose.yml

```yaml
services:
  transcribe:
    build: .
    container_name: mesin-transcribe
    restart: unless-stopped
    ports:
      - "8765:8080"
    volumes:
      - ./data/models:/data/models
      - ./data/uploads:/data/uploads
      - ./data/hasil:/data/hasil
      - ./data/config:/data/config
    environment:
      AI_ENABLED: "false"
      # TRANSCRIBE_AI_BASE_URL: http://<host-9router>:20128/v1   # aktifkan bersama AI_ENABLED=true
    mem_limit: 4g
```

### 5.3 .dockerignore

```
.venv/
.pytest_cache/
__pycache__/
*.pyc
.DS_Store
data/
uploads/*
transcribe_hasil/
sample_audio/
tests/baseline_output/
main.py
src/gui/
src/services/
```

> Catatan: `src/gui` & `src/services` di-exclude dari build context; file tetap ada di repo sebagai arsip. `tests/` sengaja **tidak** di-exclude agar unit test bisa dijalankan di dalam container (kriteria verifikasi #2).

---

## 6. Error Handling & Operasional

| Skenario | Perilaku |
|----------|----------|
| Model belum ada di cache | Download otomatis dari HuggingFace saat transcribe pertama; `/api/env.model_cached` + log "Memuat model..." (existing, R-05) |
| Download model gagal (server offline) | Error jelas di log + on_error callback; retry manual dengan klik ulang |
| `AI_ENABLED=false`, user klik tombol AI | Tombol disabled di UI; jika dipaksa via API → 503 `{detail:"Fitur AI notulen dimatikan di server ini (AI_ENABLED=false)"}` |
| Container restart saat job berjalan | Job hilang (sama seperti Ctrl+C di versi lokal); hasil/config/model aman di volume; `restart: unless-stopped` menghidupkan ulang otomatis |
| Disk host penuh (uploads/hasil menumpuk) | Didokumentasikan di README deploy: bersihkan `data/uploads/` berkala. Endpoint cleanup otomatis **ditunda** (di luar scope MVP deploy) |
| ffmpeg bermasalah | Tidak mungkin hilang (di-bake ke image); `/api/env.ffmpeg_available` tetap dicek sebagai sanity check (R-09) |
| Memory | `mem_limit: 4g` — headroom 2x dari peak terukur (~2 GB untuk model `small`; stress test existing: RSS stabil 514–522 MB pada audio 1j42m) |

---

## 7. Testing & Kriteria Verifikasi (Definition of Done)

1. **Build:** `docker build --platform linux/amd64 -t mesin-transcribe .` sukses di Mac (Apple Silicon → cross-build x86).
2. **Unit test in-container:** `docker run --rm mesin-transcribe python -m pytest tests/ -x -q` — seluruh test existing PASS, khususnya:
   - `test_wdac_patch.py` → patch urutan import + decode-via-ffmpeg jalan di Linux
   - `test_engine_smoke.py` → engine bisa dinyalakan
3. **E2E lokal:** `docker compose up` → `http://localhost:8765` → upload `sample_audio/sample_75s.mp3` → transcribe → `data/hasil/01_sample_75s/transkrip.{txt,json}` muncul di host.
4. **AI off:** tombol "Buat Notulen AI" disabled; `POST /api/notulen/ai` → 503.
5. **Persistence:** `docker compose down && up` → riwayat hasil lama tetap tampil; settings model/bahasa terakhir terpulihkan; model tidak download ulang.
6. **Di btd-server:** akses `http://btd-server:8765` dari laptop lain di LAN berhasil.

---

## 8. Risiko (pemetaan dari register existing)

| ID | Status di deployment Docker |
|----|------------------------------|
| R-02 (WDAC patch) | Tetap dimitigasi — patch dipertahankan & diverifikasi test in-container |
| R-03 (memory audio panjang) | Residual sama seperti existing; `mem_limit: 4g` sebagai pagar; streaming write tetap rekomendasi lanjutan |
| R-05 (download model tanpa indikator) | Sama seperti existing (`/api/env` + log); volume membuat download hanya sekali |
| R-09 (ffmpeg missing) | **Terverifikasi struktural** — ffmpeg di-bake ke image |
| R-15 (dependency conflict) | **Ditingkatkan** — dependensi terkunci di image, bukan lagi venv host |
| W-01 (port bentrok) | **Terverifikasi** — port mapping compose menggantikan deteksi port di app |
| W-02 (upload besar) | Sama seperti existing (chunked 1 MB); reverse proxy belum ada (LAN internal) |
| **D-NEW-01** Image besar di server lambat | Mitigasi: multi-stage build, `.dockerignore`, tanpa PySide6 → target ~1.3–1.5 GB (diverifikasi saat build) |
| **D-NEW-02** Volume permission (uid appuser vs host) | Mitigasi: folder `data/` dibuat compose dengan permission user host; didokumentasikan di README deploy |

---

## 9. Rollback Plan

- Aplikasi lama (venv lokal Windows) **tidak disentuh** — folder `firmware_transcribe` existing tetap berfungsi apa adanya.
- Artefak Docker bersifat aditif (Dockerfile, compose, requirements-docker.txt, patch paths/config/server/UI).
- Jika deployment gagal: `docker compose down`, hapus folder `data/`, kembali ke cara lama. Nol migrasi data.

---

## 10. Rekomendasi Lanjutan (di luar scope MVP deploy)

1. Streaming write segmen ke disk (R-03) untuk audio >3 jam / model lebih besar
2. Endpoint cleanup uploads otomatis (retensi 7 hari)
3. Reverse proxy (Caddy/nginx) + basic auth jika suatu saat dibuka di luar LAN
4. Evaluasi ulang multi-container (Opsi B) jika pengguna menjadi banyak
5. Bake model `small` ke image (Opsi C) jika btd-server ternyata offline
