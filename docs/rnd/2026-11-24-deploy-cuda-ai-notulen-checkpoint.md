# Checkpoint 2026-11-24 — deploy CUDA, login Google, AI notulen, hapus catatan keamanan

Status: **live di PC-AMD7900X** (`http://10.14.7.235:8765/transcribe/`), healthy.
Catatan penting: domain publik `https://dts-lab.web.id/transcribe/` **belum** menunjuk server ini.

## Ringkasan deploy

| Tahap | Image | Hasil |
|---|---|---|
| Kandidat awal | `mesin-transcribe:candidate-20261124` | overlay dari base 28/10, import OK |
| Promosi v1 | `mesin-transcribe-transcribe:latest` | produksi healthy, port 8765 |
| Rollback tag v1 | `mesin-transcribe:rollback-pre-20261124` | disimpan |
| Kandidat auth+AI | `mesin-transcribe:candidate-authai-20261124` | tes di loopback 8767 |
| Promosi v2 | `mesin-transcribe-transcribe:latest` | auth Google + AI notulen aktif |
| Rollback tag v2 | `mesin-transcribe:rollback-pre-authai-20261124` | disimpan |
| Kandidat nonotice | `mesin-transcribe:candidate-nonotice-20261124` | tes di 8766 |
| Promosi v3 | `mesin-transcribe-transcribe:latest` | catatan keamanan dihapus |
| Rollback tag v3 | `mesin-transcribe:rollback-pre-nonotice-20261124` | disimpan |

Metode: overlay `FROM mesin-transcribe-transcribe:latest` + `COPY src/ /app/src/` (dependency identik, tanpa unduh CUDA).
Sumber build: `C:\Services\mesin-transcribe-candidate`; produksi `C:\Services\mesin-transcribe`.

## Konfigurasi `.env` produksi

- Hasil merge file kredensial pengguna: **21 variabel**.
- `TRANSCRIBE_UID`/`TRANSCRIBE_GID` = `10001` (file pengguna sempat `1000` → akan gagal tulis bind mount).
- Backup: `.env.bak-20261124`.
- `AUTH_ENABLED=false` (dimatikan atas permintaan; sebelumnya `true` dengan domain `ugm.ac.id,mail.ugm.ac.id`).
- `AI_ENABLED=true`, `TRANSCRIBE_AI_BASE_URL=https://dts-lab.web.id/ngobrol_ai_router/v1`, model `BTD_worker`.
- `RESULT_RETENTION_DAYS=30` masih aktif.

## Verifikasi nyata

- Transkripsi: 2 job sukses (1.592 detik / 81 segmen; "Koordinasi BTD" 61,6 MB). Model `medium` CUDA float16, VRAM ~2,5 GB dari 16,3 GB, container ~1,26 GiB dari limit 4 GB.
- AI notulen: job `eaab67b5c660` pada folder `03_Koordinasi BTD`, `done` dalam 97,1 detik, 67.966 karakter masuk, tanpa truncation.
  Output: `NotulenAI_Koordinasi BTD.docx` (45.709 B), `.pdf` (72.447 B), `notulen_ai.md` (21.444 B), `notulen_ai.txt` (21.421 B). `transkrip.json`/`txt` tidak berubah.
  Mutu: ada ringkasan eksekutif, daftar pihak, penandaan `[tidak jelas]`, dan pernyataan jujur bahwa tanggal tidak dapat dipastikan dari ASR berkualitas rendah.
- `/api/env`: ffmpeg OK, model cached, AI router 200 OK, `key_set: true`.

## Masalah yang ditemukan dan diperbaiki

1. **OAuth state tidak valid.** Penyebab: route domain publik tidak konsisten — `/transcribe/` dilayani origin lama, `/transcribe/api/auth/callback` menghasilkan 502. Login dan callback tidak pernah sampai ke backend yang sama. **Belum diperbaiki** karena butuh akses konfigurasi Cloudflare/Tunnel.
2. **Domain publik menyajikan build lama.** Bukti: `app.js` publik 43.900 B (`Last-Modified` 9 Okt 2026) vs LAN 45.550 B (24 Nov 2026); `/api/env` publik 401 vs LAN 200. Server ini tidak punya listener 80/443, jadi Cloudflare menuju host lain.
3. **`cmd.exe /c "cd /d ... && docker compose"` gagal** lewat SSH (`no configuration file provided`). Solusi: pakai `docker compose -f <path> --env-file <path> up ...`.
4. **PowerShell inline lewat SSH memakan `$`.** Solusi: tulis `.ps1` pendek, transfer dengan `tar -cf - | ssh ... tar.exe -xf -`, jalankan `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ...`.

## Perubahan kode (commit `9423662`)

Catatan "Keamanan data: ..." di UI unggah dihapus atas permintaan pengguna.

- `src/web/templates/index.html` — blok `<p id="data-notice">` dihapus.
- `src/web/static/app.js` — pengisi `retention-note` dihapus.
- `src/web/static/style.css` — rule `.data-notice` dihapus.
- `tests/test_retention.py` — `test_ui_discloses_storage_retention_and_ai_data_flow` dihapus (assertion-nya mengunci teks yang sengaja dibuang).

Verifikasi produksi: tidak ada `Keamanan data`, `data-notice`, maupun `retention-note` di HTML/JS/CSS yang disajikan; `/api/env` 200; container healthy.
Retensi backend **tetap berjalan** — hanya teksnya yang dihapus.

## Sisa pekerjaan

1. Arahkan route Cloudflare `/transcribe/*` ke `10.14.7.235:8765` (butuh Tunnel karena IP privat). Ini sekaligus memperbaiki OAuth state. **Blocker: akses konfigurasi domain.**
2. Putuskan retensi: 2 hasil 28/10 akan terhapus otomatis sekitar 27/11. Set `RESULT_RETENTION_DAYS=0` bila mau disimpan.
3. Disk C: 39,4 GB bebas; build cache 82,8 GB (21,3 GB reclaimable) — `docker builder prune` aman, jangan hapus image/container aktif.
4. Fitur AI "rapikan transkrip" dan "dokumen resmi" (`laporan_kegiatan`, `notulen_rapat`) belum diuji end-to-end.
5. Test suite belum pernah lulus penuh lokal (`.venv-test` rusak; pytest hang pada test integrasi/model).
