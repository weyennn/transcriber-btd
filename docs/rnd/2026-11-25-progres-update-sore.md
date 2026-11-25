# Checkpoint 25 Nov 2026 (update sore)

Tidak ada kredensial atau nilai rahasia di dokumen ini.

## Produksi (PC-AMD7900X, C:\Services\mesin-transcribe)
- Image live: commit `7a44a4c` (perbaikan upload + cache asset). Rollback terakhir: `mesin-transcribe:rollback-pre-cachever-20261125`.
- Container `mesin-transcribe` healthy. Proxy up.
- Publik: `https://dts-lab.web.id/pandora/healthz` 200. Halaman memanggil `static/app.js?v=9987e61` (cache MISS, berisi perbaikan).
- Job: tidak ada yang berjalan. Riwayat: done 25, interrupted 2, error 1, cancelled 1.

## Perubahan hari ini
- `9987e61`: upload punya batas waktu 10 menit; tombol batal bekerja sebelum job dibuat; upload gagal membuka kunci tombol. Tes baru di `tests/test_web.py`.
- `7a44a4c`: nama asset diganti ke `v=9987e61` karena app.js lama tersangkut di cache Cloudflare.
- Akar masalah upload macet: browser memakai app.js lama dari cache. Request upload tidak pernah sampai server.
- Tes kandidat: 116 passed, 3 skipped, 0 gagal.
- Push `origin/main` selesai: `b7b061f..7a44a4c`, 33 commit.

## Belum selesai
- Rotasi kredensial (API key AI, Google client secret lama, session secret): menunggu persetujuan.
- Empat file `client_secret` di Downloads: belum dipindah, menunggu konfirmasi.
- Venv `/tmp/mt-venv` di Mac: masih ada, boleh dihapus.
- Login LAN `http://10.14.7.235:8765/pandora/`: redirect URI lokal belum didaftarkan di client Google.
- Job `f1031c835055` (98%, interrupted): tidak bisa dilanjutkan. Solusi: upload ulang audio. Pindah owner perlu persetujuan.
- Alur login Google penuh dengan akun asli, termasuk kolom Pencatat/Notulis: belum diuji.
- Verifikasi pascadeploy `0d87a45` (progres AI): belum tercatat.
- Kop UGM DOCX/PDF, tab 04, bar progres, keterangan retensi: belum dicek di browser.
