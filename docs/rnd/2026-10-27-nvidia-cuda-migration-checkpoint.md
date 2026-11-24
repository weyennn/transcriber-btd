# Checkpoint — persiapan migrasi GPU PC-AMD7900X

Tanggal pembaruan: 2026-10-28
Status: deployed ke `C:\\Services\\mesin-transcribe`, transkripsi GPU terverifikasi, lalu container dihentikan atas permintaan untuk mengurangi pemakaian RAM. Belum dihapus; data, image, compose project, dan rollback tag tetap tersimpan.

## Status deployment terakhir (2026-10-28)

- Server PC-AMD7900X dapat dijangkau melalui SSH alias `btd-gpu`.
- GPU host: NVIDIA GeForce RTX 5060 Ti, driver 610.88, VRAM 16 GB.
- Docker Desktop pull melalui SSH gagal karena credential helper desktop memerlukan Windows logon session; tidak diubah permanen.
- Cache cuDNN base saja tidak cukup untuk CTranslate2; percobaan pertama gagal `libcublas.so.12`. Perbaikan memasang wheel cuBLAS + cuDNN dan mengatur `LD_LIBRARY_PATH`; uji sampel berikutnya sukses.
- Mengikuti workaround Doclingo: menggunakan base image yang sudah tercache `nvidia/cuda:12.4.1-base-ubuntu22.04`, Compose `pull: false`, pasang `nvidia-cublas-cu12` dan `nvidia-cudnn-cu12` via PyPI.
- Candidate transcriber dibangun dan diuji terisolasi; awalnya gagal karena `libcublas.so.12` hilang. Setelah cuBLAS wheel ditambahkan, transkripsi sampel 75 detik berhasil dengan model small, menghasilkan `01_sample_75s/transkrip.txt` (881 byte).
- Image produksi: `mesin-transcribe-transcribe:latest`, image ID `sha256:672c2c4f9f1e5fbf63bbda63d57ddfd4ad6461c6ac87c4a3946c7ca2833edd8c`.
- Rollback image: `mesin-transcribe:rollback-pre-first-deploy-20261028`, image ID `sha256:fe0cc8c146d14f80882018950275a9cf`.
- Compose project: `C:\\Services\\mesin-transcribe`; service/container names `mesin-transcribe` dan `mesin-transcribe-proxy`; port publik `8765`, URL `/transcribe/`.
- Environment deployment dibuat server-side dengan `AUTH_ENABLED=false`, `AI_ENABLED=false`, GPU `cuda`/`float16`. Jangan menimpa `.env` saat resume.
- Setelah promosi health `/transcribe/healthz` memberi `{"ok":true}`, UI HTTP 200, CTranslate2 mengenali compute types CUDA; container GPU kandidat sebelumnya terverifikasi lewat sampel. URL deployment: `http://10.14.7.235:8765/transcribe/`.
- Pada pemeriksaan berikutnya Docker Desktop sempat restart/bermasalah. RAM bebas berubah 1.5–2.8 GB; Doclingo kemudian healthy, transcriber tidak tercantum dalam `docker ps`.
- Pemeriksaan terakhir `docker ps -a` menunjukkan `mesin-transcribe` dan `mesin-transcribe-proxy` `Exited (143)` (sekitar tujuh menit sebelum pemeriksaan). Keduanya sudah berhenti; tidak perlu stop lagi.
- Tidak ada restart Docker, penghapusan container/data, atau modifikasi server tambahan setelah itu.

## Pembaruan 2026-11-07 — perbaikan slot worker dan dugaan OOM

- Diperbaiki (lokal, belum di-commit): 409 saat worker sibuk tidak lagi jatuh 500 (`reserve_folder` mengembalikan `str`); slot transkripsi dilepas bila pembuatan job gagal; tombol Transkripsi di `app.js` memperhitungkan berkas dan status sibuk sekaligus (`workerBusy`); job AI memakai slot sendiri (`_ai_slot`), dan `worker_busy()` hanya menghitung job `transcribe`.
- Tes ringan: 48 lulus, 1 gagal yang sudah ada sebelumnya (`test_transcription_progress_uses_backend_percentage_without_offset`).
- Dugaan OOM belum terbukti: `Exited (143)` = SIGTERM, bukan 137. RAM bebas host 1,5–2,8 GB lebih kecil dari `mem_limit: 4g`. Langkah berikut: cek read-only `docker inspect` (OOMKilled), `.wslconfig`, RAM bebas, setelah disetujui pengguna.

## Resume aman

1. Baca status live dulu via approved SSH; jangan asumsikan container tetap berhenti/berjalan. `docker ps -a` dan `docker compose ps` dari `C:\\Services\\mesin-transcribe`.
2. Docker Desktop pull-auth blocker: gunakan cache lokal base image; jangan modifikasi Docker credential store. Jika build ulang diperlukan, `docker compose build --pull=false transcribe`.
3. Untuk memulai kembali saat disetujui: `docker compose up -d --no-build` dari `C:\\Services\\mesin-transcribe`; ini akan menyalakan service dan bind port 8765. Periksa RAM bebas dulu, karena host sebelumnya hanya 1.5–2.8 GB bebas.
4. Verifikasi `/transcribe/healthz`, status health container, GPU runtime, dan konfigurasi runtime. Sampel GPU pernah sukses pada candidate, tetapi service production terakhir kini stopped; uji end-to-end sesudah start jika RAM memungkinkan.
5. Untuk menghentikan lagi: `docker compose stop`; jangan `down -v` atau hapus folder data. Image rollback tetap tersedia.
6. Catatan deployment hanya berlaku pada service `mesin-transcribe`; jangan restart Docker Desktop karena dapat mengganggu Doclingo, 9router, JupyterHub, dan layanan lain.

## Perubahan fitur tambahan (lokal dan ada di image deploy)

- Mode antrean transkripsi dihapus: satu worker, request kedua saat busy ditolak atomik HTTP 409; UI menonaktifkan tombol dan menampilkan “Worker sedang digunakan”.
- Verifikasi lokal terakhir untuk no-queue dan GPU config: 12 test lulus; Python compile dan `git diff --check` lulus sebelum build.

## Candidate/deploy archive

- Candidate source sebelumnya disiapkan di `.release-stage/firmware-transcribe-gpu-candidate-20261028/`; arsip lokal dibuat sebelum update cuBLAS.
- Source lengkap hasil transfer ada di `C:\\Services\\mesin-transcribe`; file `.env` hanya di server dan rahasia tidak dicatat di checkpoint.
- Deploy memang dilakukan atas persetujuan eksplisit user; jangan ulang deploy/start tanpa memeriksa status RAM/container dan memastikan user meminta.

---

Status historis setup awal: persiapan lokal selesai, kemudian berkembang menjadi deployment seperti dicatat di atas.

## Tujuan

Menyiapkan `firmware_transcribe` agar dapat berjalan melalui Docker dengan akselerasi NVIDIA CUDA pada PC-AMD7900X (`btd-gpu`).

## Tujuan

Menyiapkan `firmware_transcribe` agar dapat berjalan melalui Docker dengan akselerasi NVIDIA CUDA pada PC-AMD7900X (`btd-gpu`).

## Perubahan lokal yang dibuat

- `Dockerfile`
  - Base image builder dan runtime diubah dari `python:3.12-slim` menjadi `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`.
  - Python serta venv `/opt/venv` dipasang di builder dan digunakan di runtime.
  - CUDA/cuDNN tersedia bagi `faster-whisper` / CTranslate2.
- `docker-compose.yml`
  - Service `transcribe` meminta GPU melalui `gpus: all`.
  - Menetapkan default runtime:
    - `TRANSCRIBE_DEVICE=cuda`
    - `TRANSCRIBE_COMPUTE_TYPE=float16`
- `src/utils/config.py`
  - Menambah `transcription_runtime()` yang membaca dua environment variable runtime.
  - Tanpa environment deployment, fallback tetap CPU/int8 untuk kompatibilitas lokal/desktop.
- `src/web/server.py`
  - Konfigurasi job transkripsi web memakai `TRANSCRIPTION_RUNTIME`; sebelumnya mengunci `cpu`/`int8`.
- `tests/test_config.py`
  - Menambah test runtime GPU dan fallback CPU.
- `tests/test_vulkan_benchmark_compose.py`
  - Menambah guard test bahwa compose meminta GPU dan Dockerfile memakai CUDA/cuDNN.
- `DEPLOY.md`
  - Diperbarui untuk prasyarat NVIDIA, mode CUDA default, fallback CPU, dan bukti verifikasi GPU.

## Verifikasi lokal

Berhasil dijalankan:

```text
python3 -m pytest tests/test_config.py tests/test_vulkan_benchmark_compose.py -q
9 passed in 0.09s

python3 -m py_compile src/utils/config.py src/web/server.py
GPU compose static validation: PASS
git diff --check
```

`graphify update .` juga telah berhasil; graph di `graphify-out/` diperbarui.

## Batasan yang belum dapat diverifikasi

- Docker daemon lokal Mac tidak aktif (`~/.docker/run/docker.sock` tidak tersedia), sehingga image CUDA belum dapat dibangun atau diuji secara lokal.
- Server PC-AMD7900X belum diakses pada tahap setup ini. Percobaan SSH sebelumnya berakhir timeout; tidak ada file, image, container, service, atau konfigurasi server yang diubah.
- Kesesuaian CUDA versi dengan driver NVIDIA/Docker Desktop server belum dapat dibuktikan sampai server tersedia.

## Langkah lanjutan saat server dapat dijangkau

1. Jalankan inspeksi read-only dengan SSH profile wajib:
   ```sh
   /usr/bin/ssh -F /Users/wayeien/.hermes/profiles/btdgpu/ssh/config btd-gpu powershell.exe -NoProfile -Command "..."
   ```
2. Verifikasi Docker/Compose, `nvidia-smi`, kapasitas disk/RAM, port target, dan service yang sudah ada.
3. Uji GPU runtime Docker dalam kandidat non-produksi:
   ```text
   docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
   ```
4. Transfer sumber beku dan bandingkan hash deployment-critical files.
5. Build image kandidat bertag baru, jangan menimpa image yang sedang melayani produksi.
6. Jalankan kandidat pada port loopback yang kosong dengan data sementara.
7. Buktikan CUDA dari dalam kandidat (`nvidia-smi`, konfigurasi `cuda`/`float16`) dan jalankan transkripsi sampel.
8. Simpan rollback tag, lalu promosi hanya setelah health, UI, dan transkripsi kandidat tervalidasi.

## Catatan operasional

- Satu worker transkripsi dipertahankan karena model GPU dapat berebut VRAM bila paralel.
- CUDA mempercepat inferensi Whisper; upload, ekspor, dan I/O tetap dominan CPU/disk.
- Fallback diagnosis CPU:
  ```text
  TRANSCRIBE_DEVICE=cpu
  TRANSCRIBE_COMPUTE_TYPE=int8
  ```
