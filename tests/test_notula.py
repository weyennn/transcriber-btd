"""Notula bentuk Peraturan Rektor UGM Nomor 21 Tahun 2023, Lampiran I butir 22."""
import shutil

import pytest
from docx import Document

from src.pandora_documents import notula

MD = """# Notulensi Rapat Koordinasi Layanan Digital

- Hari, tanggal: Senin, 24 November 2026
- Pukul: 09.00 - 10.30 WIB
- Tempat: Ruang Rapat Rektorat
- Pemimpin Rapat: Dr. Budi Santoso, Kepala Biro
- Pencatat/Notulis: tidak disebutkan dalam rekaman
- Durasi sumber: 1.592 detik

## Acara

1. Evaluasi progres layanan
2. Kesiapan infrastruktur

## Peserta Rapat

1. Biro Teknologi
2. Pusat Data

## Kegiatan Rapat

### 1. Pembukaan

Rapat dibuka oleh pimpinan rapat.

### 2. Pembahasan

#### 2.1 Evaluasi progres

- Antarmuka sudah diuji internal.
- Perlu perbaikan unggah berkas besar.

### 3. Kesimpulan

- Uji coba dimulai terbatas.

| Tindak Lanjut | Penanggung Jawab | Tenggat |
|---|---|---|
| Menyiapkan uji coba | Pusat Data | Belum ditentukan |
"""


def test_uraikan_memetakan_semua_keterangan_notula():
    n = notula.uraikan(MD, catatan="Catatan AI.")
    assert n.rapat == "Koordinasi Layanan Digital"
    assert n.hari_tanggal == "Senin, 24 November 2026" and n.pukul == "09.00 - 10.30 WIB"
    assert n.tempat == "Ruang Rapat Rektorat" and n.pemimpin.startswith("Dr. Budi")
    assert n.notulis == ""                                  # "tidak disebutkan" menjadi isian titik-titik
    assert n.acara == ["Evaluasi progres layanan", "Kesiapan infrastruktur"]
    assert n.peserta == ["Biro Teknologi", "Pusat Data"]
    assert [j for j, _ in n.kegiatan] == ["1. Pembukaan", "2. Pembahasan", "3. Kesimpulan"]
    assert "Durasi" not in str(n)                           # keterangan di luar format tidak ikut tercetak


def test_uraikan_menerima_susunan_lama_tanpa_kegiatan_rapat():
    lama = "# Notulen Rapat X\n\n## Ringkasan\n\nIsi ringkas.\n\n## Keputusan\n\n- Setuju.\n"
    n = notula.uraikan(lama)
    assert n.rapat == "X"
    assert [j for j, _ in n.kegiatan] == ["1. Ringkasan", "2. Keputusan"]


def test_sumber_typst_memuat_ketentuan_peraturan_rektor():
    sumber = notula.sumber_typst(notula.uraikan(MD, catatan="C"))
    assert "top: 3cm, bottom: 3.5cm, left: 2.5cm, right: 2cm" in sumber          # butir 34
    assert '"Times New Roman"' in sumber and "size: 12pt" in sumber               # butir 32
    assert "rgb(0, 30, 98)" in sumber and "UNIVERSITAS GADJAH MADA" in sumber     # kop butir 2
    assert "dy: -1.5cm" in sumber and "dx: -0.5cm" in sumber                       # lambang 1,5 cm dari atas, 2 cm dari kiri
    assert "[NOTULA]" in sumber and "counter(page).get().first() > 1" in sumber     # nomor halaman mulai halaman 2
    for kata in ("Hari, tanggal", "Pukul", "Tempat", "Acara", "Pemimpin Rapat", "Pencatat/Notulis",
                 "Peserta Rapat", "Kegiatan Rapat", "NIP/NIKA"):
        assert kata in sumber, kata
    assert "#isian" in sumber                                                       # pencatat kosong -> titik-titik


def test_docx_mengikuti_ukuran_kertas_huruf_dan_batas(tmp_path):
    jalur = notula.bentuk_docx(notula.uraikan(MD, catatan="C"), tmp_path / "n.docx")
    doc = Document(jalur)
    seksi = doc.sections[0]
    assert round(seksi.top_margin.cm, 1) == 3 and round(seksi.bottom_margin.cm, 1) == 3.5
    assert round(seksi.left_margin.cm, 1) == 2.5 and round(seksi.right_margin.cm, 1) == 2
    assert seksi.different_first_page_header_footer is True                         # kop hanya halaman pertama
    assert doc.styles["Normal"].font.name == "Times New Roman" and doc.styles["Normal"].font.size.pt == 12
    kop = "\n".join(c.text for r in seksi.first_page_header.tables[0].rows for c in r.cells)
    assert "UNIVERSITAS GADJAH MADA" in kop and "Bulaksumur" in kop
    assert "PAGE" in seksi.header.paragraphs[0]._p.xml                              # nomor halaman halaman berikutnya
    isi = "\n".join(c.text for r in doc.tables[0].rows for c in r.cells)
    for kata in ("Rapat", "Hari, tanggal", "Pukul", "Tempat", "Acara", "Pemimpin Rapat", "Pencatat/Notulis",
                 "Peserta Rapat", "Kegiatan Rapat", "1. Pembukaan", "2. Pembahasan", "3. Kesimpulan"):
        assert kata in isi, kata
    assert "." * 30 in isi                                                            # pencatat tak disebut -> isian titik-titik
    teks = "\n".join(p.text for p in doc.paragraphs)
    assert "NOTULA" in teks and "NIP/NIKA" in teks and "Pemimpin Rapat" in teks


def test_unit_kerja_dapat_dicantumkan_pada_kop(tmp_path):
    n = notula.uraikan(MD, unit="Biro Teknologi Digital")
    assert "Biro Teknologi Digital".upper() in "\n".join(
        c.text for r in Document(notula.bentuk_docx(n, tmp_path / "u.docx")).sections[0].first_page_header.tables[0].rows
        for c in r.cells)
    assert '"Biro Teknologi Digital"' in notula.sumber_typst(n)


def test_pdf_terbentuk_dan_logo_sementara_dibersihkan(tmp_path):
    if not shutil.which("typst"):
        pytest.skip("typst tidak terpasang")
    jalur = notula.bentuk_pdf(notula.uraikan(MD, catatan="C"), tmp_path / "n.pdf")
    assert (tmp_path / "n.pdf").read_bytes()[:4] == b"%PDF" and jalur.endswith("n.pdf")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["n.pdf"]                    # tidak ada .typ/logo tertinggal


def test_catatan_ai_ada_di_kaki_halaman_bukan_di_isi(tmp_path):
    catatan = "Catatan: isi dokumen ini dihasilkan dengan bantuan AI."
    n = notula.uraikan(MD, catatan=catatan)
    sumber = notula.sumber_typst(n)
    assert "footer:" in sumber and sumber.count(catatan) == 1       # satu kali, di pengaturan kaki halaman
    assert sumber.index(catatan) < sumber.index("[NOTULA]")         # bukan di badan dokumen
    doc = Document(notula.bentuk_docx(n, tmp_path / "n.docx"))
    seksi = doc.sections[0]
    assert catatan in seksi.footer.paragraphs[0].text and catatan in seksi.first_page_footer.paragraphs[0].text
    assert catatan not in "\n".join(p.text for p in doc.paragraphs)  # tidak di isi dokumen


def test_pdf_memuat_catatan_ai_di_setiap_halaman(tmp_path):
    if not shutil.which("typst") or not shutil.which("pdftotext"):
        pytest.skip("typst/pdftotext tidak terpasang")
    import subprocess
    panjang = MD + "\n".join(f"- Butir pembahasan tambahan nomor {i} yang cukup panjang agar dokumen melewati satu halaman." for i in range(60))
    n = notula.uraikan(panjang.replace("### 3. Kesimpulan", "- tambahan\n\n### 3. Kesimpulan"), catatan="CATATAN-UJI-KAKI")
    jalur = notula.bentuk_pdf(n, tmp_path / "n.pdf")
    halaman = subprocess.run(["pdftotext", "-layout", jalur, "-"], capture_output=True, text=True).stdout.split("\f")
    halaman = [h for h in halaman if h.strip()]
    assert len(halaman) >= 2 and all("CATATAN-UJI-KAKI" in h for h in halaman)
