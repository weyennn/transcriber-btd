"""Notulen dan transkrip rapi dari AI memakai tampilan naskah dinas yang sama dengan dokumen resmi."""
from docx import Document

from src.pandora_documents import render

NOTULEN = """# Notulen Rapat Koordinasi Layanan Digital

- Tanggal: tidak disebutkan dalam rekaman
- **Waktu**: [tidak jelas]
- Durasi sumber: 1.592 detik

## 1. Ringkasan Eksekutif

Rapat menyepakati uji coba terbatas.

## 2. Pihak yang Hadir

- Pusat Data
- Humas

### Pembicara

- Pimpinan rapat

## 7. Action Items

| Prioritas | Action | Owner |
|---|---|---|
| Tinggi | Uji coba | Pusat Data |
"""


def test_judul_dan_kepala_diambil_dari_markdown():
    n = render.naskah_dari_markdown(NOTULEN, "Notulen Rapat", "Notulis", catatan="C")
    assert n.judul == "Koordinasi Layanan Digital"            # "Notulen Rapat" sudah jadi jenis dokumen
    assert n.kepala_tetap == [("Tanggal", "tidak disebutkan dalam rekaman"),
                              ("Waktu", "[tidak jelas]"), ("Durasi sumber", "1.592 detik")]
    assert [(b.nomor, b.judul) for b in n.bagian] == [("1", "Ringkasan Eksekutif"),
                                                       ("2", "Pihak yang Hadir"), ("7", "Action Items")]
    assert "### Pembicara" in n.bagian[1].isi                 # anak judul tetap di dalam bagiannya


def test_kepala_dan_judul_bisa_ditentukan_pemanggil():
    n = render.naskah_dari_markdown("Teks tanpa judul.\n", "Transkrip Rapi", judul="01_rapat",
                                    kepala=[("Sumber", "01_rapat")])
    assert n.judul == "01_rapat" and n.kepala_tetap == [("Sumber", "01_rapat")]
    assert len(n.bagian) == 1 and n.bagian[0].judul == "" and "Teks tanpa judul." in n.bagian[0].isi


def test_pdf_source_menyorot_ringkasan_dan_tidak_mengulang_judul():
    n = render.naskah_dari_markdown(NOTULEN, "Notulen Rapat", "Notulis", catatan="C")
    sumber = render.sumber_typst(n)
    assert "luma(240)" in sumber                       # ringkasan eksekutif dalam kotak
    assert sumber.count("Koordinasi Layanan Digital") == 1
    assert "#let ada-ttd = true" in sumber and '"Notulis"' in sumber


def test_tanpa_penanda_tangan_ruang_tanda_tangan_dilewati(tmp_path):
    n = render.naskah_dari_markdown("Isi.\n", "Transkrip Rapi", penanda_tangan=None, judul="X")
    assert "#let ada-ttd = false" in render.sumber_typst(n)
    jalur = render.bentuk_docx(n, tmp_path / "t.docx")
    teks = "\n".join(p.text for p in Document(jalur).paragraphs)
    assert "Notulis" not in teks and "." * 30 not in teks


def test_docx_ringkasan_berlatar_dan_tidak_ada_penanda_akhir(tmp_path):
    n = render.naskah_dari_markdown(NOTULEN, "Notulen Rapat", "Notulis", catatan="Catatan AI.")
    doc = Document(render.bentuk_docx(n, tmp_path / "n.docx"))
    teks = "\n".join(p.text for p in doc.paragraphs)
    assert "Akhir Dokumen" not in teks and "Catatan AI." in teks
    ringkasan = next(p for p in doc.paragraphs if p.text.startswith("Rapat menyepakati"))
    assert ringkasan._p.pPr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}shd") is not None
    assert len(doc.tables) == 2                         # kepala dokumen + tabel action items
    assert "PAGE" in doc.sections[0].footer.paragraphs[0]._p.xml


def test_pdf_terbentuk_bila_typst_ada(tmp_path):
    import shutil
    import pytest
    if not shutil.which("typst"):
        pytest.skip("typst tidak terpasang")
    n = render.naskah_dari_markdown(NOTULEN, "Notulen Rapat", "Notulis", catatan="C")
    jalur = render.bentuk_pdf(n, tmp_path / "n.pdf")
    assert (tmp_path / "n.pdf").read_bytes()[:4] == b"%PDF" and jalur.endswith("n.pdf")


TABEL = """# Notulen Rapat Uji

## 1. Action Items

| Prioritas | Action / Deliverable | Owner |
|---|---|---|
| Tinggi | Menyiapkan lingkungan uji coba terisolasi untuk dua unit percontohan, termasuk akun pengguna dan kuota penyimpanan | Pusat Data dan Teknologi Informasi |
| Sedang | Menyusun pedoman | Belum ditentukan |
| Rendah | Mengkaji retensi | Humas |
"""


def test_lebar_kolom_mengikuti_isi_dan_garis_antarbaris():
    rows = [["Prioritas", "Action", "Owner"], ["Tinggi", "x" * 120, "Pusat Data dan Teknologi Informasi"]]
    rencana = render.lebar_kolom(rows)
    assert rencana[0][0] == "auto" and rencana[1][0] == "fr" and rencana[2][0] == "fr"
    assert rencana[1][1] > rencana[2][1]                      # kolom paling panjang mendapat porsi terbesar
    assert render.lebar_kolom([["A", "B"], ["1", "2"]]) == [("fr", 1.0), ("fr", 1.0)]   # semua pendek: sama rata
    n = render.naskah_dari_markdown(TABEL, "Notulen Rapat", "Notulis")
    sumber = render.sumber_typst(n)
    assert "columns: (auto, " in sumber and "fr" in sumber
    assert sumber.count("table.hline(stroke: .25pt") == 2     # antarbaris isi (3 baris isi -> 2 pemisah)


def test_anak_judul_dibedakan_dan_kotak_ringkasan_tanpa_menjorok():
    n = render.naskah_dari_markdown(NOTULEN, "Notulen Rapat", "Notulis")
    sumber = render.sumber_typst(n)
    assert "#set par(first-line-indent: 0em)" in sumber       # di dalam kotak ringkasan
    templat = render.TEMPLATE_PATH.read_text(encoding="utf-8")
    assert 'style: "italic"' in templat                       # anak judul tebal-miring


def test_docx_tabel_lebar_proporsional_baris_tak_terpotong_dan_judul_berulang(tmp_path):
    n = render.naskah_dari_markdown(TABEL, "Notulen Rapat", "Notulis")
    doc = Document(render.bentuk_docx(n, tmp_path / "t.docx"))
    tabel = doc.tables[-1]
    lebar = [sel.width for sel in tabel.rows[1].cells]
    assert lebar[1] > lebar[0]                                # kolom Action lebih lebar dari Prioritas
    xml = tabel._tbl.xml
    assert xml.count("w:cantSplit") == 4 and xml.count("w:tblHeader") == 1
