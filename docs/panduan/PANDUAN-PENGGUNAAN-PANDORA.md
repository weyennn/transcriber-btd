# Panduan Penggunaan Pandora

**Pandora — Transcriber Audio UGM** adalah aplikasi web untuk mengubah rekaman audio rapat, kegiatan, dan wawancara menjadi teks. Dari teks itu, Pandora dapat merapikan transkrip, menyusun notulensi, dan menyusun dokumen resmi berbentuk naskah dinas.

> **Status panduan:** draf. Sesuaikan dengan keputusan terbaru sebelum dibagikan.

---

## 1. Sebelum mulai

### Yang Anda perlukan

- Browser modern (Chrome, Edge, atau Firefox).
- Akun UGM (`@ugm.ac.id` atau `@mail.ugm.ac.id`). Login memakai Google.
- Berkas audio dengan format `.mp3`, `.wav`, `.m4a`, `.flac`, `.aac`, atau `.ogg`.

### Yang perlu diketahui

- **Transkripsi berjalan satu per satu.** Hanya satu pekerjaan transkripsi yang diproses pada satu waktu. Bila sedang ada pekerjaan lain, tunggu sampai selesai.
- **Hasil hanya milik Anda.** Hasil transkripsi, notulensi, dan dokumen disimpan per akun. Pengguna lain tidak dapat melihatnya.
- **Fitur AI perlu diaktifkan admin.** Rapikan transkrip, notulensi, dan dokumen resmi hanya tampil bila layanan AI di server aktif. Bila tombolnya tidak bisa diklik, hubungi admin.
- **Keluaran AI perlu diperiksa.** Notulensi dan dokumen disusun dari rekaman, tetapi tetap bisa keliru. Sebelum dibagikan, cocokkan keputusan, angka, dan nama dengan transkrip asli.

---

## 2. Masuk ke Pandora

1. Buka alamat Pandora yang diberikan admin.
2. Pada halaman pembuka, klik **Buka Pandora**.
3. Login dengan akun UGM Anda.

Setelah masuk, Anda langsung melihat area unggah dan panel pengaturan.

---

## 3. Mentranskripsi rekaman

### Langkah 1: Pilih berkas audio

- Seret berkas ke kotak unggah, atau klik kotaknya untuk memilih berkas.
- Setelah berkas terpilih, namanya dan ukurannya tampil.
- Untuk membatalkan pilihan sebelum mulai, klik **Hapus file**. Tindakan ini hanya menghapus pilihan di browser Anda, bukan berkas di server.

### Langkah 2: Atur pengaturan (opsional)

| Pengaturan | Pilihan | Keterangan |
|---|---|---|
| Model | `tiny`, `base`, `small`, `medium` | Semakin besar model, semakin teliti, tetapi semakin lama |
| Bahasa | `id` (Indonesia), `en` (Inggris) | Pilih sesuai bahasa rekaman |

Pilihan terakhir Anda tersimpan dan dipakai lagi saat Anda kembali.

### Langkah 3: Mulai transkripsi

1. Klik **Transcribe**.
2. Pantau panel **Status**. Progres dan pesan ditampilkan di sana.
3. Panel **Log dan segmen** menampilkan potongan teks secara langsung.
4. Bila ingin menghentikan, klik **Batal**.

Rekaman panjang (1 sampai 3 jam) dapat diproses. Lama prosesnya bergantung pada panjang rekaman dan model yang dipilih.

---

## 4. Membaca hasil

Setelah transkripsi selesai, panel **Hasil** aktif. Hasil dapat dilihat lewat tab berikut:

| Tab | Isi | Dibuat oleh |
|---|---|---|
| **Asli** | Transkrip mentah, sesuai hasil mesin | Otomatis |
| **JSON** | Segmen dan metadata, untuk keperluan teknis | Otomatis |
| **Rapi AI** | Transkrip yang sudah dirapikan | Tombol **Rapikan transkrip** |
| **Notulensi** | Notulensi rapat yang tersusun | Tombol **Buat notulensi rapat** |
| **Dokumen** | Naskah dinas resmi | Tombol **Susun dokumen resmi** |

Tombol untuk tab AI baru aktif setelah layanan AI tersedia.

**Catatan penting:** **Rapikan transkrip** tidak mengubah transkrip asli. Hasil rapi disimpan sebagai berkas terpisah, sehingga transkrip asli tetap bisa dibuka kembali.

---

## 5. Merapikan transkrip

1. Buka tab **Asli** atau **Hasil**.
2. Klik **Rapikan transkrip**.
3. Tunggu sampai status selesai, lalu buka tab **Rapi AI**.

Gunakan hasil rapi untuk membaca lebih nyaman. Untuk tujuan resmi, rujuk transkrip asli.

---

## 6. Membuat notulensi rapat

1. Klik **Buat notulensi rapat**.
2. Tunggu proses selesai. Proses ini bisa memakan beberapa menit.
3. Buka tab **Notulensi** untuk membaca pratinjau.
4. Unduh hasilnya sebagai berkas Word (`.docx`).

Notulensi disusun dengan bagian: ringkasan, pembahasan, keputusan, dan tindak lanjut. Sebelum dibagikan, periksa bahwa:

- keputusan yang tertulis memang diputuskan dalam rapat, bukan hanya diusulkan;
- nama dan jabatan yang tercantum memang disebut dalam rekaman;
- tenggat dan penanggung jawab sesuai dengan transkrip.

---

## 7. Menyusun dokumen resmi

Fitur ini menghasilkan naskah dinas dari transkrip. Pandora menyediakan dua jenis dokumen.

| Jenis | Bagian dokumen |
|---|---|
| **Laporan Kegiatan** | Dasar dan maksud, pelaksanaan, hasil yang dilaporkan, kendala dan catatan perbedaan, tindak lanjut, penutup |
| **Notulen Rapat** | Ringkasan rapat, peserta dan pihak yang disebut, pokok pembahasan, keputusan, tindak lanjut, penutup |

### Langkah

1. Buka tab **Dokumen**, lalu klik **Susun dokumen resmi**.
2. Pilih **jenis dokumen**.
3. Isi **judul**. Judul awal diambil dari nama folder hasil, dan bisa diubah.
4. Isi kolom kepala sesuai jenisnya, misalnya **Hari, tanggal**, **Tempat**, **Unit penyusun**, atau **Pimpinan rapat**.
5. Klik **Susun dokumen**.

### Yang perlu diketahui tentang dokumen resmi

- **Kolom kepala diisi oleh Anda.** Pandora tidak mengarang tanggal, tempat, atau nama pejabat. Kosongkan kolom yang tidak diketahui.
- **Angka harus disebut dalam rekaman.** Bila sebuah angka tidak disebut, angka itu tidak akan ditulis.
- **Bagian yang tidak jelas ditandai.** Bagian rekaman yang tidak terdengar jelas ditulis sebagai `[tidak jelas]`, bukan ditebak.
- **Dokumen bisa ditolak.** Bila naskah tidak lolos pemeriksaan (cakupan sumber, bentuk naskah, atau keterlacakan), Pandora menampilkan alasannya dan tidak menyatakan dokumen selesai. Anda dapat mencoba lagi atau menyesuaikan transkrip.
- **Dokumen belum sah.** Laporan Kegiatan memerlukan pengesahan pejabat berwenang. Notulen disusun dari rekaman dan tetap perlu ditinjau notulis.

### Hasil dokumen

Setelah berhasil, tersedia tiga berkas:

- **`.md`** untuk teks mentah.
- **`.pdf`** untuk dicetak atau dibagikan. Berkas ini hanya tersedia bila perkakas pembuat PDF terpasang di server.
- **`.docx`** untuk diedit di Word.

---

## 8. Riwayat hasil

Panel **Riwayat** menampilkan semua folder hasil Anda, dengan format `01_nama`, `02_nama`, dan seterusnya.

- Klik salah satu folder untuk membuka hasilnya lagi.
- Bila notulensi atau dokumen belum dibuat, tombolnya tetap tersedia di sana.
- Untuk menghapus riwayat, klik ikon hapus pada folder yang dimaksud. Pandora meminta konfirmasi terlebih dahulu. Setelah dihapus, semua berkas di dalam folder itu ikut hilang dan tidak dapat dikembalikan.

---

## 9. Cara cepat (satu siklus kerja)

1. Masuk ke Pandora.
2. Pilih berkas audio dan atur bahasa serta model.
3. Klik **Transcribe**, lalu tunggu.
4. Baca tab **Asli**.
5. Klik **Rapikan transkrip** bila perlu.
6. Klik **Buat notulensi rapat**, lalu periksa dan unduh DOCX.
7. Bila perlu dokumen resmi, klik **Susun dokumen resmi**, isi kepala, lalu unduh.

---

## 10. Masalah umum

| Gejala | Kemungkinan penyebab | Yang bisa dilakukan |
|---|---|---|
| Tombol AI tidak bisa diklik | Layanan AI belum aktif di server | Hubungi admin |
| Login gagal | Akun bukan `@ugm.ac.id` atau `@mail.ugm.ac.id` | Gunakan akun UGM |
| Berkas tidak bisa diunggah | Format tidak didukung | Ubah ke `.mp3`, `.wav`, `.m4a`, `.flac`, `.aac`, atau `.ogg` |
| Transkripsi tidak mulai, muncul pesan "Worker sedang digunakan" | Ada transkripsi lain yang sedang berjalan, di akun mana pun | Tunggu sampai selesai, lalu coba lagi |
| Log menampilkan teks yang sama berulang | Bagian hening atau bunyi tidak jelas | Periksa bagian itu di rekaman; lanjutkan bila hasil lain wajar |
| Dokumen ditolak pemeriksa | Naskah tidak lolos cakupan atau bentuk | Baca alasan yang ditampilkan, lalu coba lagi |
| Notulensi tidak selesai | Layanan AI sibuk atau tidak tersedia | Coba lagi beberapa saat kemudian; hubungi admin bila tetap gagal |

---

## 11. Batas dan kehati-hatian

- **Data rapat bersifat rahasia.** Unggah hanya rekaman yang boleh diproses. Ketentuan penggunaan data mengikuti kebijakan instansi.
- **Keluaran AI bukan keputusan.** Notulensi dan dokumen adalah bahan kerja. Keputusan dan pengesahan tetap berada pada pejabat yang berwenang.
- **Jangan membagikan tautan akun.** Akses Pandora mengikuti akun Anda.

---

## Bantuan

Bila menemui masalah yang tidak tercantum di sini, catat langkah yang dilakukan, pesan yang muncul, dan nama folder hasil, lalu hubungi admin Pandora.
