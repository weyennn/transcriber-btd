# Kerangka Bahan Ajar — Belajar Bersama: Menambah Modul Penyusunan Dokumen pada Pandora

> **Status: tidak dipakai.** Kerangka ini untuk pengembang dan sudah digantikan oleh handbook pengguna di `bahan-ajar/` (sumber: `docs/panduan/PANDUAN-PENGGUNAAN-PANDORA.md`, 28 halaman, edisi November 2026). Dibiarkan sebagai catatan.
> **Status awal:** draf kerangka, belum disetujui. Belum ada isi bab.
> **Sumber utama:** `HANDOFF-PANDORA-MODUL-DOKUMEN-20261009.pdf` (3 halaman, 9 Okt 2026), penuntun "belajar bersama". Bagian kode yang dirujuk: `src/pandora_documents/`, `src/pandora_quality/`, dan `src/web/`, `src/notulen/`, `src/core/` di repo ini.
> **Sumber pendukung:** memori proyek Pandora (keputusan dan status per 7 Nov 2026), hanya bila perlu.
> **Sasaran (usulan):** pengembang atau teknisi yang akan menambah modul dokumen di Pandora, serta peserta kajian internal.
> **Format akhir (usulan):** modul LaTeX bergaya UGM lewat skill `bahan-ajar-modul`, setelah kerangka disetujui.

## Yang perlu dipastikan sebelum menulis isi

- **Konfirmasi sasaran dan panjang.** Penuntun aslinya ringkas (3 halaman). Modul bisa dibuat padat atau diperluas menjadi buku.
- **Data server tidak masuk modul.** Penuntun memuat alamat IP server, nama pengguna SSH, dan nomor registry proyek. Semuanya dihapus dari modul.
- **Angka harus dicek ulang.** Angka di penuntun (baris 144, 8.192 token, 180.000 karakter, 117, 361) berasal dari 9 Okt. Sebelum dicetak, cek lagi terhadap `src/notulen/ai_generator.py` dan `src/export/typst_converter.py`, karena kode sudah berubah sejak itu (lihat status 7 Nov).
- **Status pekerjaan.** Penuntun menyebut ada bagian yang belum dikerjakan dan menjadi milik pemilik kode. Modul harus menandai mana yang sudah jadi, mana yang belum.
- **Jalur kode publik.** Penuntun membandingkan repo publik `weyennn/transcriber-btd` dengan salinan di server. Modul tidak menyebut jalur lokal pengguna.
- **Lisensi font.** DejaVu Serif dan Typst (`templates/naskah-dinas.typ`) dicek sebelum modul dibagikan ke luar.

## Peta bab (usulan)

| Bab | Judul | Isi utama | Sumber |
|---|---|---|---|
| I | Pendahuluan | Mengapa perlu belajar dari kode yang benar-benar berjalan, bukan dari repo publik saja | Penuntun, pembuka |
| II | Membandingkan dengan Kode Publik | Langkah pertama: membandingkan berkas per berkas, dan pelajaran "berkas sama ukuran belum tentu sama isi" | Penuntun bagian 1 |
| III | Memahami Arsitektur | Susunan berlapis dari peramban sampai DOCX/PDF, tiga sifat arsitektur yang menentukan cara menambah fitur | Penuntun bagian 2 |
| IV | Menemukan yang Menghalangi | Empat temuan dengan bukti baris kode dan akibatnya bagi modul | Penuntun bagian 3 |
| V | Mengikuti Pola yang Sudah Ada | Lima pola aplikasi dan cara modul mengikutinya (konfigurasi env, panggilan model, penyimpanan per akun, pekerjaan latar, perkakas image) | Penuntun bagian 4 |
| VI | Membangun Modul | Berkas per berkas: `pandora_quality/` dan `pandora_documents/`, serta alasan setiap berkas | Penuntun bagian 5 |
| VII | Menguji dan Memeriksa | Demo rencana, cakupan, hasil pemeriksaan, dan naskah dinas | `checks.py`, `demo_rakit.py`, `slop_gate.py` |
| VIII | Penutup | Ringkasan pelajaran, apa yang belum dikerjakan, tindak lanjut | Penuntun, bagian yang belum dikerjakan |

Bab materi menjadi Bab II–VII. Bab I dan VIII adalah kerangka pembuka dan penutup.

## Indikator keberhasilan (draf)

- **Bab II:** pembaca dapat menjelaskan mengapa perbandingan ukuran saja tidak cukup untuk menilai berkas.
- **Bab III:** pembaca dapat menggambar ulang alur dari peramban ke PDF dan menyebut tiga sifat arsitektur.
- **Bab IV:** pembaca dapat menjelaskan dua temuan (pemotongan transkrip dan batas token) beserta baris kodenya dan akibatnya bagi modul.
- **Bab V:** pembaca dapat menyebut lima pola dan menunjukkan satu contoh pengikutan pola di kode.
- **Bab VI:** pembaca dapat menjelaskan peran satu berkas di `pandora_documents/` tanpa melihat penuntun.
- **Bab VII:** pembaca dapat menjalankan `demo_rakit.py` dan membaca hasil pemeriksaan naskah.

## Benang merah

Penuntun ini sudah berbentuk cerita, yaitu langkah demi langkah sampai ke keputusan. Modul bisa menjaga alur itu dengan satu contoh berjalan: seorang pengembang yang menambah modul penyusunan naskah dari rekaman rapat. Ia menemukan pemotongan transkrip di `ai_generator.py:37` dan harus memutuskan apakah modulnya memanggil model per bagian atau tidak. Ini perlu konfirmasi, karena penuntun asli tidak memakai tokoh.

## Latihan yang diusulkan

- Latihan 1 (Bab II): bandingkan satu berkas yang ukurannya sama dengan repo publik dan catat apakah isinya sama.
- Latihan 2 (Bab III): gambar ulang alur dari `server.py` ke `docx_converter.py`.
- Latihan 3 (Bab IV): cari baris pemotongan transkrip di kode, lalu jelaskan akibatnya untuk laporan panjang.
- Latihan 4 (Bab VI): tambahkan satu aturan baru ke `rules.json` dan jalankan `slop_gate.py` (tanpa menyentuh kode Python).

## Pertanyaan yang perlu dijawab sebelum menulis

1. Sasaran utamanya pengembang, atau staf yang menggunakan Pandora? Ini menentukan bahasa dan kedalaman kode.
2. Apakah angka dari 9 Okt dipakai apa adanya sebagai bukti historis, atau diperbarui ke kode terbaru?
3. Apakah benang merah "modul penyusunan naskah dari rekaman rapat" disetujui?
4. Apakah penuntun cukup sebagai sumber tunggal, atau memori proyek Pandora boleh dirujuk juga?

Setelah Anda menjawab, saya tulis bab per bab. Repo tidak diubah selain berkas kerangka ini.
