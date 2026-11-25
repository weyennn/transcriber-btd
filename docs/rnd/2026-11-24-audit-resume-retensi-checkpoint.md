# Checkpoint 2026-11-24 — audit transcriber, lanjutkan transkripsi, retensi 30 hari

Status: kode selesai dan ter-commit lokal (belum di-push, **belum di-deploy**). Server tidak diubah.

## Titik simpan (commit di `main`, di atas `b7b061f`)
| Commit | Isi |
|---|---|
| `048c2ad` | build: Vulkan AMD diganti NVIDIA CUDA ala Doclingo; `.env.example`; hapus benchmark Vulkan |
| `ba7a00a` | mesin: pembatalan, progres dan teks sementara per bagian, titik simpan + lanjutkan, bahasa otomatis, validasi chunk |
| `b6e2221` | AI: terjemahan halus ke Indonesia, catatan kaki hasil buatan AI |
| `759c099` | web: worker tunggal, endpoint dan tombol lanjutkan, `/healthz` jujur, retensi 30 hari, catatan data di UI |

Pembagian per lapisan modul (bukan per topik) karena berkas web saling terkait; kerja GPU dan slot worker sebelumnya ikut di commit 4.

## Keputusan pengguna
- Vulkan AMD ditinggalkan; konfigurasi disamakan dengan Doclingo (NVIDIA CUDA).
- Pecah file besar: pilih hasil sebagian + progres per bagian, lalu fitur lanjutkan setelah gagal. Proses terpisah per bagian dan ukuran bagian otomatis tidak dikerjakan.
- Deploy ditunda ("belum, tunda dulu"). Login Google (nomor 1 audit) belum diputuskan.

## Temuan server (read-only, 2026-11-24, PC-AMD7900X)
- GO untuk 4 GB / medium float16 / 1 worker. RAM host bebas 7,7 GB dari 15,1; VM Docker dibatasi ~10,7 GiB (tanpa `.wslconfig`); VRAM bebas 15,65 GB; data Docker di `D:\Docker\data\wsl\disk\docker_data.vhdx` (336,8 GB, D: bebas 366 GB, C: bebas 39,5 GB).
- `mesin-transcribe`: `OOMKilled=false`, `ExitCode=143` (stop manual 2026-10-28). Dugaan OOM terbantahkan.
- Risiko: doclingo (limit 9 GiB) dan transcribe (4 GB) berbagi VM ~10,7 GiB.
- Doclingo sehat (HTTP 200); port 8765 bebas; image `mesin-transcribe-transcribe:latest` dan rollback `...rollback-pre-first-deploy-20261028` ada.

## Perubahan fungsional
- Audit: status SQLite tak lagi menggagalkan job; unggahan dihapus setelah job (kecuali gagal yang bisa dilanjutkan; disapu 7 hari); pembatalan diperiksa antar tahap; progres ditulis saat persen berubah; SSE di kolam thread sendiri; `/healthz` 503 bila ffmpeg/GPU rusak; nama berkas panjang dipotong; `TRANSCRIBE_CHUNK_SECONDS` divalidasi.
- Lanjutkan: `transkrip_sebagian.json` per bagian; `POST /api/jobs/{id}/resume`; tombol di UI muncul setelah error dalam sesi yang sama.
- Bahasa: opsi "Otomatis" (deteksi sekali, lalu dikunci). Terjemahan ke Indonesia lewat prompt AI; Whisper tidak menerjemahkan.
- Catatan kaki AI di notulen, transkrip rapi, dokumen resmi, unduhan transkrip. `transkrip.txt` sengaja tidak diubah.
- Retensi: `RESULT_RETENTION_DAYS` (default 30 hanya bila `DATA_DIR` diset; `0` = mati); hasil dan riwayat job lama dihapus tiap 6 jam; catatan keamanan data di UI.

## Verifikasi
Tes ringan per berkas dengan batas waktu dan `HF_HUB_OFFLINE=1`; tiap commit diuji di snapshot `git archive`. Gagal sejak sebelum perubahan (bukan dari pekerjaan ini): `test_transcribe_smoke` dan `test_upload_and_transcribe_sse` (butuh model), `test_generate_notulen_docx` (tergantung `typst` lokal). Belum diuji: Whisper + GPU sungguhan, UI di browser, mutu terjemahan LLM, RAM nyata di server.

## Sisa pekerjaan
1. Deploy bertahap dengan izin: cek read-only `C:\Services\mesin-transcribe` (umur data hasil), kandidat terisolasi + 1 sampel di GPU + ukur RAM/VRAM, baru produksi.
2. **Sebelum deploy:** retensi akan langsung menghapus hasil server yang lebih tua dari 30 hari; set `RESULT_RETENTION_DAYS=0` bila perlu cadangan.
3. Putuskan login Google (data bersama saat `AUTH_ENABLED=false`); cek teks catatan keamanan di UI (alur data ke layanan AI).
4. Opsional: tombol lanjutkan di riwayat dan setelah restart; lepas model dari VRAM saat idle; `beam_size` 5 untuk GPU; `large-v3-turbo`.
5. Revisi 4 (template tata naskah UGM) belum dikerjakan; push ke GitHub belum.
6. `bahan-ajar/`, `docs/bahan-ajar/`, `docs/panduan/` belum dilacak git (di luar pekerjaan ini).

Tidak ada arsip zip dan tidak ada salinan ke SSD.
