"""Kepala naskah dinas UGM (Peraturan Rektor Nomor 21 Tahun 2023, Lampiran I butir 2) dan tata halamannya.

Dipakai bersama oleh Notula, dokumen resmi, dan transkrip rapi supaya semua dokumen hasil AI
berkepala sama:
  - lambang UGM 2 x 2 cm, 1,5 cm dari tepi atas dan 2 cm dari tepi kiri, hanya di halaman pertama;
  - "UNIVERSITAS GADJAH MADA" Times New Roman 16, alamat Arial 10, berwarna RGB 0,30,98;
    bila ada unit kerja (PANDORA_KOP_UNIT), namanya dicetak tebal pada baris kedua;
  - batas atas 3 cm, bawah 3,5 cm, kiri 2,5 cm, kanan 2 cm; Times New Roman 12;
  - nomor halaman di tengah atas, tidak dicantumkan pada halaman pertama (Pasal 47).
"""

from __future__ import annotations

import os
from pathlib import Path

FONT_DOCX = "Times New Roman"

LOGO_PATH = Path(__file__).resolve().parents[1] / "web" / "static" / "assets" / "logo-ugm.png"
ALAMAT_UGM = ("Bulaksumur, Yogyakarta 55281, Telepon +62274 562011, 588688,",
              "Faksimile +62274 562011, 565223, Laman: http://ugm.ac.id, Posel: setr@ugm.ac.id")
BIRU_KOP = (0, 30, 98)

# Tata halaman lama (tanpa kop) yang masih dipakai pembentuk PDF lama (src/export/typst_converter.py).
ATUR_HALAMAN_LAMA = '''#set page(
  paper: "a4",
  margin: (top: 2.5cm, bottom: 2.5cm, left: 2.5cm, right: 2.5cm),
  numbering: "1",
  number-align: center,
)

#set text(font: ("DejaVu Serif", "Times New Roman", "Libertinus Serif"), size: 11pt, lang: "id")'''

ATUR_HALAMAN_KOP = '''#set page(
  paper: "a4",
  margin: (top: 3cm, bottom: 3.5cm, left: 2.5cm, right: 2cm),
  header: context {
    if counter(page).get().first() > 1 { align(center, counter(page).display("1")) }
  },
  header-ascent: 40%,
)

#set text(font: ("Times New Roman", "Liberation Serif", "Libertinus Serif", "DejaVu Serif"), size: 12pt, lang: "id")'''


def unit_kop() -> str:
    """Nama fakultas/sekolah/unit kerja pada baris kedua kop; kosong = kop UGM saja."""
    return os.environ.get("PANDORA_KOP_UNIT", "").strip()


def _str(teks: str) -> str:
    aman = str(teks).replace("\\", "\\\\").replace('"', '\\"')
    return '"' + " ".join(aman.split()) + '"'


def typst_kop(logo: str, unit: str = "") -> str:
    """Kode Typst kop surat: diletakkan di luar alur halaman, lalu diberi jarak sebelum isi."""
    return f'''#let biru = rgb({BIRU_KOP[0]}, {BIRU_KOP[1]}, {BIRU_KOP[2]})
#let unit-kop = {_str(unit)}

// Kop surat: 1,5 cm dari tepi atas kertas dan 2 cm dari tepi kiri (isi dimulai 3 cm dari tepi atas).
#place(top + left, dx: -0.5cm, dy: -1.5cm, float: false, {{
  set text(fill: biru)
  grid(
    columns: (2cm, 15.5cm), column-gutter: 0.4cm, align: horizon,
    image({_str(logo)}, width: 2cm, height: 2cm),
    {{
      set par(leading: 0.35em, spacing: 0.35em, first-line-indent: 0em)
      if unit-kop != "" {{
        text(size: 16pt)[UNIVERSITAS GADJAH MADA]
        linebreak()
        text(size: 16pt, weight: "bold", upper(unit-kop))
      }} else {{
        text(size: 16pt, weight: "bold")[UNIVERSITAS GADJAH MADA]
      }}
      linebreak()
      text(font: ("Arial", "Liberation Sans", "DejaVu Sans"), size: 10pt)[#{_str(ALAMAT_UGM[0])} #linebreak() #{_str(ALAMAT_UGM[1])}]
    }},
  )
}})

#v(1.6cm)'''


def docx_kop(doc, seksi, unit: str = "") -> float:
    """Pasang kop di header halaman pertama, nomor halaman di header halaman berikutnya, dan batas halaman.

    Mengembalikan lebar isi dalam cm.
    """
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    seksi.page_width, seksi.page_height = Cm(21), Cm(29.7)
    seksi.top_margin, seksi.bottom_margin = Cm(3), Cm(3.5)
    seksi.left_margin, seksi.right_margin = Cm(2.5), Cm(2)
    seksi.header_distance = Cm(1.5)
    seksi.different_first_page_header_footer = True
    lebar_isi = 21 - 2.5 - 2
    biru = RGBColor(*BIRU_KOP)

    def jalankan(par, teks, tebal=False, ukuran=None, font=None):
        run = par.add_run(teks)
        run.bold = tebal
        run.font.name = font or FONT_DOCX
        run._element.rPr.rFonts.set(qn("w:eastAsia"), font or FONT_DOCX)
        if ukuran:
            run.font.size = Pt(ukuran)
        run.font.color.rgb = biru
        return run

    header_pertama = seksi.first_page_header
    tabel = header_pertama.add_table(1, 2, Cm(lebar_isi))
    tabel.autofit = False
    kiri, kanan = tabel.rows[0].cells
    kiri.width, kanan.width = Cm(2.6), Cm(lebar_isi - 2.6)
    kiri.paragraphs[0].add_run().add_picture(str(LOGO_PATH), width=Cm(2), height=Cm(2))
    teks = kanan.paragraphs[0]
    if unit:
        jalankan(teks, "UNIVERSITAS GADJAH MADA", ukuran=16)
        jalankan(kanan.add_paragraph(), unit.upper(), tebal=True, ukuran=16)
    else:
        jalankan(teks, "UNIVERSITAS GADJAH MADA", tebal=True, ukuran=16)
    for baris in ALAMAT_UGM:
        jalankan(kanan.add_paragraph(), baris, ukuran=10, font="Arial")
    for par in kanan.paragraphs:
        par.paragraph_format.space_after = Pt(0)
    header_pertama.paragraphs[0].paragraph_format.space_after = Pt(0)

    nomor = seksi.header.paragraphs[0]
    nomor.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = nomor.add_run()
    for jenis_medan, isi in (("begin", None), (None, "PAGE"), ("end", None)):
        if jenis_medan:
            medan = OxmlElement("w:fldChar")
            medan.set(qn("w:fldCharType"), jenis_medan)
        else:
            medan = OxmlElement("w:instrText")
            medan.set(qn("xml:space"), "preserve")
            medan.text = isi
        run._r.append(medan)
    run.font.name = FONT_DOCX
    run.font.size = Pt(12)
    return lebar_isi
