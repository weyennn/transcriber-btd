# Checkpoint 25 Nov 2026 (akhir hari)

Status ringkas. Tidak ada kredensial atau nilai rahasia di dokumen ini.

## Produksi (PC-AMD7900X, C:\Services\mesin-transcribe)
- Image: mesin-transcribe-transcribe:latest dari commit 5d4f96d (HEAD lokal).
- Rollback terakhir: mesin-transcribe:rollback-pre-uiclean-20261125.
- Healthy. https://dts-lab.web.id/pandora/healthz -> {"ok":true}.
- Login Google aktif (AUTH_ENABLED). /pandora/api/auth/me tanpa login -> 401.
- Job aktif: tidak ada. Gate job: done 25, interrupted 2, error 1, cancelled 1.

## Yang sudah live
- Login session Google (callback https://dts-lab.web.id/pandora/api/auth/callback).
- Nama Pencatat/Notulis dari akun Google yang login (bb3b75d).
- Reset bar progres saat job AI mulai (1314e40).
- Keterangan "dihapus setelah 30 hari" di Riwayat, angka dari RESULT_RETENTION_DAYS (d87292e).
- Kop UGM bersama untuk Notula, dokumen resmi, dan transkrip rapi (9ab611f).
- Navigasi header dihapus (84f8cbb).
- Tab 04 / HASIL: unduhan MD dihapus; tombol Salin hanya di tab Asli dan JSON (5d4f96d).

## Verifikasi
- Kandidat container: test_web, document_render, naskah_markdown, notula, notulis_login, ai_generator, retention, auth -> 115 passed, 3 skipped, 0 gagal.
- Mac (venv sementara, faster-whisper terpasang): 118 passed, 0 gagal.
- Produksi (cek anonim): healthz OK; app.js tanpa tombol MD; ada reset progres dan setRetentionNote; tanpa class nav.

## Belum selesai / menunggu keputusan
- Push origin/main: 30 commit belum di-push. Menunggu persetujuan.
- Rotasi kredensial (API key AI, Google client secret, session secret): belum dilakukan. Nilai pernah tampil di docker inspect.
- Cache Cloudflare untuk /pandora/static/app.js: HIT, berlaku sampai ~4 jam. Purge manual atau Ctrl+F5.
- Job f1031c835055 (98%, interrupted): tidak bisa di-resume; perlu upload ulang audio. Pindah owner job lama butuh persetujuan.
- Login LAN http://10.14.7.235:8765/pandora/: redirect URI lokal belum terdaftar.
- Tes login Google asli belum dilakukan: buat satu notula, cek kolom Pencatat dan kop di DOCX/PDF.
- Empat file client_secret lain di ~/Downloads belum dipindah.
- Venv sementara /tmp/mt-venv di Mac: bisa dihapus.

## Catatan proses
- Script promosi di server (promote-identitas.ps1) sekarang berhenti jika gate menemukan job running/pending/queued.
- Setiap promosi: gate job -> tag rollback -> docker compose up -d --no-build transcribe -> hapus kandidat.
