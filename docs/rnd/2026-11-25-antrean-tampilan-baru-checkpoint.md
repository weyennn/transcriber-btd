# Checkpoint 2026-11-25 — antrean transkripsi, tampilan baru, unggah teks

Status: semua di `main` lokal. **Belum di-push, belum di-deploy.** Server tidak disentuh hari ini
(koneksi ke server belum tersedia; pengujian di server menunggu).

## Titik simpan (commit lokal di atas `ccbc9f7`)

| Commit | Isi |
|---|---|
| `15253a9` | Unggah transkrip .txt/.md untuk notulensi AI (`POST /api/notulen/from-text`, batas `MAX_TEXT_BYTES` 5 MB); bahasa Otomatis jadi bawaan |
| `1d23d01` | Rapikan jarak, font, tombol; hapus label kecil di atas judul |
| `d79860b` | Antrean: dua transkripsi paralel, sisanya menunggu (FIFO) |
| `88c3e7c` | Antrean di UI (catatan antrean, tombol mulai tidak terkunci) |
| `9df4e91` | Tampilan baru dari `~/Downloads/pandora.html` (biru-navy, Plus Jakarta Sans) |
| `c149f1a` | Halaman masuk baru (`login-f.html`), keadaan kosong hasil, status lingkungan disembunyikan |
| `1dee0a2` | Template dokumen: notulen AI dan transkrip rapi memakai `render.py` (tampilan naskah dinas) |
| `f1ba22b` | Perbaikan UX: hint tombol, gulir ke hasil, riwayat bersih + tanggal + filter dinamis, hero dan "Mode lokal" dihapus |

## Belum terlacak git

`docs/contoh-dokumen/` (7 contoh dengan placeholder), checkpoint 24 dan 25 Nov, `bahan-ajar/`, `docs/bahan-ajar/`, `docs/panduan/`.

## Antrean transkripsi (d79860b)

- `MAX_CONCURRENT_TRANSCRIBE` 2 (1-4), `MAX_TRANSCRIBE_QUEUE` 20, `MAX_TRANSCRIBE_PER_USER` 2 (keputusan pengguna: dari 3 jadi 2).
  Selebihnya ditolak HTTP 429. Variabel ada di `docker-compose.yml`, `.env.example`, `DEPLOY.md`.
- Satu model Whisper dipakai bersama (`num_workers` = konkurensi), dimuat dengan kunci agar tidak dobel.
- Job menunggu: status `pending`, `queue_position`, pesan "Menunggu antrean · urutan N"; dibatalkan saat menunggu
  membuang unggahan dan folder kosong. Job menunggu saat service restart menjadi `interrupted`.
- `/api/jobs/worker-status` -> `running/waiting/capacity/max_waiting/per_user/busy`.
- Mode tanpa login: semua pengguna dihitung satu orang, jadi batas per pengguna berlaku untuk semua.

## Tampilan

- Desain dari dua berkas pengguna: `pandora.html` (aplikasi) dan `login-f.html` (halaman masuk). Semua ID dan perilaku lama dipertahankan.
- Font dihost sendiri di `src/web/static/assets/fonts` (Plus Jakarta Sans, JetBrains Mono, Fraunces; subset latin, OFL).
- Fitur desain tanpa backend sengaja tidak dipasang: kamus istilah, banyak berkas, nama pembicara, pemutar audio, edit transkrip,
  ringkasan cepat, template notulensi, ekspor SRT/VTT.
- Skill Impeccable terpasang global di `~/.claude/skills/impeccable`; temuan detektor yang tersisa menyangkut identitas
  halaman masuk (judul miring, label kecil, cahaya tombol) dan sengaja dibiarkan.

## Template dokumen (1dee0a2)

- `naskah_dari_markdown()` / `NaskahMarkdown` di `src/pandora_documents/render.py`: judul dari `#`, butir "Label: nilai" di bawah judul jadi kepala dokumen,
  setiap `##` jadi bagian. Notulen AI (jenis "Notulen Rapat", TTD "Notulis") dan Transkrip Rapi AI (tanpa TTD) memakainya; `src/export/*` tidak lagi dipakai keluaran AI.
- Ringkasan Eksekutif disorot (kotak abu-abu muda); tabel: kolom pendek selebar isi, kolom panjang membagi sisa, garis tipis antarbaris;
  DOCX: baris tak terpotong, judul kolom berulang; anak judul tebal-miring dan menjorok.
- Risiko: PDF server memakai DejaVu Serif (container hanya `fonts-dejavu`), beda dari render laptop; DOCX belum dilihat di Word;
  baris tabel panjang di PDF masih bisa terpotong antarhalaman; teks tebal AI dihapus; belum mengikuti pedoman tata naskah UGM.

## Belum diuji (menunggu server)

- Notulen/dokumen AI sungguhan dengan template baru (PDF di server, DOCX di Word)
- Dua transkripsi paralel di GPU sungguhan (kecepatan, VRAM; RAM container 4 GB bersama doclingo).
- Tampilan saat transkripsi berjalan, menunggu antrean, dan gagal; tampilan di ponsel sungguhan.
- Unggah video, bahasa Otomatis, mutu terjemahan, lanjutkan-transkripsi, unggah teks dengan AI sungguhan.

## Sisa pekerjaan

1. **Retensi:** 2 hasil 28/10 terhapus otomatis ~27/11; set `RESULT_RETENTION_DAYS=0` di `.env` server bila mau disimpan.
2. Pasang font setara Times di image; uji di server saat tersambung, lalu deploy bertahap (kandidat terisolasi dulu). Cek `.env` server: nilai di sana menimpa bawaan baru.
3. Keputusan login Google (juga menentukan keadilan batas per pengguna).
4. Push ke GitHub; commit berkas yang belum terlacak.
5. Revisi 4 (templat laporan UGM) dan 8 (panduan tata kelola AI) belum.
6. Uji lokal: jalankan tes per berkas (`timeout`, `HF_HUB_OFFLINE=1`); menjalankan `test_web` dan `test_hardening` dalam satu perintah bentrok pada database tes (sudah ada sejak sebelumnya).
