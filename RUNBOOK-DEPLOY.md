# RUNBOOK-DEPLOY.md — Deploy Mesin Transcribe ke btd-server

Runbook end-to-end: transfer dari Mac → build di btd-server → verifikasi DoD → go-live LAN.
Referensi: `DEPLOY.md` (operasional harian), spec `docs/superpowers/specs/2026-09-11-docker-deployment-design.md`.

> **Isi variabel dulu sebelum mulai** — ganti sesuai server:
>
> | Variabel | Contoh | Keterangan |
> |---|---|---|
> | `SERVER` | `user@btd-server` atau `user@192.168.x.x` | SSH target |
> | `REMOTE_DIR` | `/opt/mesin-transcribe` | Folder repo di server |

---

## Langkah 0 — Preflight (dari Mac)

Cek kesiapan server tanpa mengubah apa pun:

```bash
SERVER=user@btd-server          # ← GANTI
REMOTE_DIR=/opt/mesin-transcribe # ← GANTI

ssh $SERVER '
  echo "== OS & arch =="; uname -a
  echo "== Docker =="; docker --version && docker compose version
  echo "== Daemon =="; docker info --format "{{.ServerVersion}} (OK)"
  echo "== Port 8765 =="; (ss -tlnp 2>/dev/null | grep 8765 || echo "bebas")
  echo "== Disk =="; df -h / | tail -1
'
```

**Gate:** semua OK sebelum lanjut —
- Docker Engine + plugin compose terinstal, daemon jalan
- Port 8765 bebas
- Disk bebas ≥ 5 GB (image ~1.5 GB + model ~460 MB + data)

## Langkah 1 — Dapatkan repo di server

Repo sudah di-push ke GitHub: `https://github.com/weyennn/transcriber-btd.git`

**Opsi A — clone di server (disarankan):**

```bash
ssh $SERVER "git clone https://github.com/weyennn/transcriber-btd.git $REMOTE_DIR"
```

> Branch default `main` sudah berisi seluruh hasil dockerization (merge `45bfc33`).

> Repo private? Pakai SSH remote (`git@github.com:weyennn/transcriber-btd.git`) dengan deploy key di server, atau credential HTTPS yang sudah tersimpan.

**Opsi B — rsync dari Mac** (kalau server tidak bisa akses GitHub; folder build/venv besar tidak ikut):

```bash
cd /Users/wayeien/Documents/firmware_transcribe

rsync -avz --delete \
  --exclude '.git' --exclude '.venv*' --exclude '__pycache__' \
  --exclude 'data' --exclude 'hasil' --exclude 'models' \
  --exclude '.superpowers' --exclude 'docs' \
  ./ $SERVER:$REMOTE_DIR/
```

> Alternatif tanpa rsync: `tar czf - --exclude=.git --exclude='.venv*' --exclude=data . | ssh $SERVER "mkdir -p $REMOTE_DIR && tar xzf - -C $REMOTE_DIR"`

**Verifikasi di server:**

```bash
ssh $SERVER "ls $REMOTE_DIR && cat $REMOTE_DIR/docker-compose.yml | head -20"
```

Harus terlihat: `Dockerfile`, `docker-compose.yml`, `verify_deploy.sh`, `src/`, `tests/`, `sample_audio/`.

## Langkah 2 — Build + verifikasi otomatis (di server)

`verify_deploy.sh` menjalankan seluruh DoD spec §7 berurutan (7 langkah):
build → unit test in-container → compose up → `/api/env` → E2E transcribe
sample_75s → AI-off 503 → persistence setelah restart.

```bash
ssh -t $SERVER "cd $REMOTE_DIR && chmod +x verify_deploy.sh && ./verify_deploy.sh"
```

- **Pertama kali ±30 menit** (build image + download model `small` ~460 MB).
- Script idempotent — gagal di tengah? Perbaiki, jalankan ulang. `data/` tidak dihapus.
- Jika transfer pakai Windows line endings: `ssh $SERVER "sed -i 's/\r$//' $REMOTE_DIR/verify_deploy.sh"` dulu.

**Gate — output terakhir harus:**

```
════════════════════════════════════════════════════════════════
  SEMUA VERIFIKASI LULUS (7/7 langkah)
════════════════════════════════════════════════════════════════
```

## Langkah 3 — Verifikasi akses LAN (dari Mac/laptop lain)

DoD spec §7 butir 6 — server harus bisa diakses dari mesin lain di LAN:

```bash
# Ganti IP sesuai server
curl -s http://<ip-server>:8765/healthz        # {"ok":true}
curl -s http://<ip-server>:8765/api/env | python3 -m json.tool
```

Lalu buka di browser: `http://<ip-server>:8765`
- Dashboard tampil
- Badge **"AI notulen nonaktif"** + tombol 🤖 disabled (D-5)

Kalau curl dari laptop gagal tapi dari server OK → kemungkinan firewall:

```bash
ssh $SERVER 'sudo ufw allow 8765/tcp 2>/dev/null || sudo firewall-cmd --add-port=8765/tcp --permanent && sudo firewall-cmd --reload 2>/dev/null || echo "cek firewall manual"'
```

## Langkah 4 — Serah terima

Deployment selesai. Catat untuk tim:

| Item | Nilai |
|---|---|
| URL dashboard | `http://<ip-server>:8765` |
| Folder server | `$REMOTE_DIR` |
| Hasil transkrip | `$REMOTE_DIR/data/hasil/` |
| Stop / start | `docker compose down` / `docker compose up -d` |
| Log | `docker compose logs -f` |
| Update versi | rsync ulang (Langkah 1) → `docker compose up -d --build` |
| Aktifkan AI notulen | lihat `DEPLOY.md` §"Mengaktifkan AI Notulen" |
| Verifikasi ulang kapan saja | `./verify_deploy.sh` (idempotent) |

---

## Rollback

Perubahan bersifat aditif — rollback = matikan container, tidak ada state host yang tercemar:

```bash
ssh $SERVER "cd $REMOTE_DIR && docker compose down"
# Hapus total (termasuk hasil transkrip!):
# rm -rf $REMOTE_DIR && docker rmi mesin-transcribe
```

## Troubleshooting

| Gejala | Cek |
|---|---|
| Build gagal di layer pip | Koneksi server ke pypi; coba ulang (layer ter-cache) |
| `/healthz` tidak merespons 60 dtk | `docker compose logs --tail=100` — biasanya ffmpeg/libgomp |
| Transkripsi lambat / OOM | Normal CPU int8; cek `docker stats` vs `mem_limit 4g` |
| Model download ulang tiap restart | Volume `./data/models` tidak ter-mount — cek `docker compose config` |
| Port bentrok | Ubah mapping di `docker-compose.yml`: `"<port-baru>:8080"` |
| Browser tidak bisa akses dari LAN | Langkah 3 firewall; pastikan container listen `0.0.0.0` (default uvicorn di Dockerfile) |
