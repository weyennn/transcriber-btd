# DEPLOY.md — Runbook Mesin Transcribe di btd-server

Dashboard web transkripsi audio (faster-whisper, CPU-only) via Docker.

## Prasyarat

- Docker Engine + plugin `docker compose` (cek: `docker compose version`)
- Port **8765** bebas di host (atau set `TRANSCRIBE_HOST_PORT`)
- URL publik memakai subpath `/transcribe/`; proxy internal meneruskan ke FastAPI di port 8080
- Koneksi internet **satu kali** untuk download model whisper `medium` saat transkripsi pertama
- Folder `data/` dapat ditulis oleh UID/GID container (default `1000:1000`)

## Quick Start

```bash
# 1. Salin repo ke server (git clone / scp), lalu masuk ke folder repo
cd firmware_transcribe

# 2. Siapkan volume state dan permission (sesuaikan UID/GID bila perlu)
mkdir -p data/{models,uploads,hasil,config}
export TRANSCRIBE_UID="$(id -u)" TRANSCRIBE_GID="$(id -g)"

# 3. Verifikasi otomatis penuh (build + test + E2E, ±30 menit pertama kali)
./verify_deploy.sh

# Atau langsung jalan tanpa verifikasi:
# docker compose up -d
```

Buka dashboard: `http://<ip-server>:${TRANSCRIBE_HOST_PORT:-8765}/transcribe/`

## Environment Variables

| Variabel | Default (Docker) | Keterangan |
|---|---|---|
| `DATA_DIR` | `/data` | Root state: uploads, hasil, models |
| `CONFIG_DIR` | `/data/config` | Lokasi `config.json` (persistence settings) |
| `AI_ENABLED` | `false` | Feature flag notulen AI (D-5). `true` untuk mengaktifkan |
| `HF_HOME` | `/data/models` | Cache model whisper (download sekali) |
| `PORT` | `8080` (container) → host port | Port server di dalam container |
| `TRANSCRIBE_HOST_PORT` | `8765` | Port dashboard di host |
| `TRANSCRIBE_UID` / `TRANSCRIBE_GID` | `1000` / `1000` | Identitas proses untuk bind mount `data/` |
| `MAX_UPLOAD_BYTES` | `2147483648` | Batas upload dalam byte |
| `TRANSCRIBE_AI_BASE_URL` | — | Endpoint OpenAI-compatible |
| `TRANSCRIBE_AI_MODEL` | — | Nama model untuk notulen AI |
| `TRANSCRIBE_AI_API_KEY` | — | API key endpoint AI |
| `AUTH_ENABLED` | `false` | `true` untuk mewajibkan Login with Google |
| `APP_BASE_PATH` | `/transcribe` | Prefix aplikasi publik |
| `GOOGLE_CLIENT_ID` | — | Google OAuth client ID dari secret manager |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret dari secret manager |
| `GOOGLE_REDIRECT_URI` | `https://dts-lab.web.id/transcribe/api/auth/callback` | Harus sama persis dengan Google Console |
| `SESSION_SECRET` | — | Secret acak panjang; wajib jika auth aktif |
| `SESSION_DAYS` | `7` | Masa berlaku signed session |
| `AUTH_ALLOWED_DOMAIN` | `ugm.ac.id` | Domain akun Google yang diizinkan |
| `AUTH_ALLOWED_EMAILS` | — | Allowlist email tambahan, dipisah koma |
| `AUTH_COOKIE_SECURE` | `true` | Wajib `true` untuk HTTPS production |

### Mengaktifkan Login with Google

Untuk deployment publik HTTPS, set `AUTH_ENABLED=true` dan suplai seluruh secret melalui
secret manager/runtime environment. Jangan commit nilai credential ke repo atau `.env`.

Authorized redirect URI di Google Cloud Console harus persis:

```text
https://dts-lab.web.id/transcribe/api/auth/callback
```

Mode lokal memakai `AUTH_ENABLED=false` dan tidak memerlukan Google credential. Endpoint
`/healthz` tetap publik; endpoint upload, transkripsi, history, download, delete, job, dan
AI wajib memiliki session valid saat auth aktif.

Semua env runtime utama diatur di `docker-compose.yml`.

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

- **Batas memori** container 4GB (`mem_limit` di compose).
- **Tanpa GPU** — transkripsi berjalan di CPU (int8), model default `medium`; `small` tetap tersedia sebagai opsi lebih ringan.
- **Port host** dapat diubah dengan `TRANSCRIBE_HOST_PORT=9876 docker compose up -d`.
- **Permission volume**: compose menjalankan proses sebagai `${TRANSCRIBE_UID:-1000}:${TRANSCRIBE_GID:-1000}`. Set kedua env tersebut ke UID/GID pemilik `data/` bila default tidak sesuai.
- **Data penting** (aman dari `docker compose down`):
  - `data/hasil/` — hasil transkrip (transkrip.txt/json, notulen DOCX)
  - `data/config/` — settings terakhir
  - `data/models/` — cache model
