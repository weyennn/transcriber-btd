# DEPLOY.md — Runbook Mesin Transcribe di btd-server

Dashboard web transkripsi audio (faster-whisper, CPU-only) via Docker.

## Prasyarat

- Docker Engine + plugin `docker compose` (cek: `docker compose version`)
- Port **8765** bebas di host
- Koneksi internet **satu kali** untuk download model whisper `small` (~460MB) saat transkripsi pertama

## Quick Start

```bash
# 1. Salin repo ke server (git clone / scp), lalu masuk ke folder repo
cd firmware_transcribe

# 2a. Verifikasi otomatis penuh (build + test + E2E, ±30 menit pertama kali)
./verify_deploy.sh

# 2b. Atau langsung jalan tanpa verifikasi
docker compose up -d
```

Buka dashboard: `http://<ip-server>:8765`

## Environment Variables

| Variabel | Default (Docker) | Keterangan |
|---|---|---|
| `DATA_DIR` | `/data` | Root state: uploads, hasil, models |
| `CONFIG_DIR` | `/data/config` | Lokasi `config.json` (persistence settings) |
| `AI_ENABLED` | `false` | Feature flag notulen AI (D-5). `true` untuk mengaktifkan |
| `HF_HOME` | `/data/models` | Cache model whisper (download sekali) |
| `PORT` | `8080` (container) → `8765` (host) | Port server |
| `TRANSCRIBE_AI_BASE_URL` | — | Endpoint OpenAI-compatible (mis. 9router `http://<host>:20128/v1`) |
| `TRANSCRIBE_AI_MODEL` | — | Nama model untuk notulen AI |
| `TRANSCRIBE_AI_API_KEY` | — | API key endpoint AI (jika perlu) |

Semua env diatur di `docker-compose.yml` bagian `environment:`.

## Mengaktifkan AI Notulen (nanti)

1. Edit `docker-compose.yml`:
   ```yaml
   environment:
     AI_ENABLED: "true"
     TRANSCRIBE_AI_BASE_URL: http://<host-9router>:20128/v1
     # TRANSCRIBE_AI_MODEL: <nama-model>
     # TRANSCRIBE_AI_API_KEY: <key>
   ```
2. Terapkan ulang:
   ```bash
   docker compose up -d --force-recreate
   ```

## Operasional

```bash
# Lihat log realtime
docker compose logs -f

# Stop server (data tetap aman)
docker compose down

# Update ke versi terbaru
git pull && docker compose up -d --build

# Bersih-bersih file upload yang menumpuk (hasil TIDAK ikut terhapus)
rm -f data/uploads/*
```

## Catatan

- **Model whisper** tersimpan di `data/models/` — didownload sekali saat transkripsi pertama (~460MB untuk `small`); jangan dihapus kecuali ingin download ulang.
- **Batas memori** container 4GB (`mem_limit` di compose).
- **Tanpa GPU** — transkripsi berjalan di CPU (int8), model `small` cukup untuk bahasa Indonesia.
- **Data penting** (aman dari `docker compose down`):
  - `data/hasil/` — hasil transkrip (transkrip.txt/json, notulen DOCX)
  - `data/config/` — settings terakhir
  - `data/models/` — cache model
- Verifikasi ulang kapan saja dengan `./verify_deploy.sh` (idempotent, tidak menghapus `data/`).
