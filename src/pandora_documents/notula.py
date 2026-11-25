"""Notula bentuk Peraturan Rektor UGM Nomor 21 Tahun 2023 (Lampiran I, butir 22).

Susunan yang dipenuhi:
  kepala     kop UGM (lambang, nama universitas, alamat) pada halaman pertama
  pembuka    kata NOTULA huruf kapital, simetris
  isi        Rapat, Hari, tanggal, Pukul, Tempat, Acara, Pemimpin Rapat, Pencatat/Notulis,
             Peserta Rapat, lalu Kegiatan Rapat: 1. Pembukaan, 2. Pembahasan, 3. Kesimpulan
  penutup    "Pemimpin Rapat", nama jabatan, tanda tangan dan cap, nama pejabat, NIP/NIKA di kanan
Format: A4, Times New Roman 12, batas atas 3 cm, bawah 3,5 cm, kiri 2,5 cm, kanan 2 cm;
nomor halaman simetris di tengah atas dan tidak dicantumkan pada halaman pertama.

Yang tidak dapat dipenuhi oleh berkas: kertas HVS putih tulang (pilihan saat mencetak) dan
kata penyambung di sudut kanan bawah tiap halaman (butir 33).

Isi bersumber dari Markdown hasil AI. Keterangan yang tidak disebut dalam rekaman dicetak
sebagai titik-titik untuk diisi tangan; tidak pernah dikarang.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from src.pandora_documents import kop
from src.pandora_documents.render import PerkakasTidakTersedia, _str, _tabel_typst, urai

TEMPLATE_PATH = Path(__file__).with_name("templates") / "notula-ugm.typ"
LOGO_PATH = kop.LOGO_PATH
ALAMAT_UGM = kop.ALAMAT_UGM
TITIK = "." * 60
FONT_DOCX = "Times New Roman"

_TIDAK_DISEBUT = re.compile(r"^(tidak (disebut|jelas|diketahui|ada)|belum (ditentukan|disebut)|\[tidak jelas\]|-|—)", re.I)
_LABEL = {
    "hari": "hari_tanggal", "hari, tanggal": "hari_tanggal", "hari dan tanggal": "hari_tanggal", "tanggal": "hari_tanggal",
    "pukul": "pukul", "waktu": "pukul",
    "tempat": "tempat", "lokasi": "tempat", "format/lokasi": "tempat",
    "pemimpin rapat": "pemimpin", "pemimpin": "pemimpin", "pimpinan rapat": "pemimpin", "pimpinan": "pemimpin",
    "pencatat/notulis": "notulis", "pencatat": "notulis", "notulis": "notulis",
    "rapat": "rapat", "nama rapat": "rapat",
}


@dataclass
class Notula:
    rapat: str = ""
    hari_tanggal: str = ""
    pukul: str = ""
    tempat: str = ""
    pemimpin: str = ""
    notulis: str = ""
    acara: list[str] = field(default_factory=list)
    peserta: list[str] = field(default_factory=list)
    kegiatan: list[tuple[str, str]] = field(default_factory=list)   # (judul, isi Markdown)
    catatan: str = ""
    unit: str = ""


def _bersih(teks: str) -> str:
    return re.sub(r"[*_`]", "", teks).strip()


def _nilai(teks: str) -> str:
    """Keterangan yang dinyatakan tidak ada dalam rekaman dikosongkan agar jadi isian titik-titik."""
    teks = _bersih(teks)
    return "" if not teks or _TIDAK_DISEBUT.match(teks) else teks


def _daftar(isi: str) -> list[str]:
    butir: list[str] = []
    for blok in urai(isi):
        if blok[0] in ("butir", "nomor"):
            butir.extend(blok[1])
        elif blok[0] == "paragraf" and blok[1]:
            butir.append(blok[1])
    return [b for b in (_nilai(x) for x in butir) if b]


def uraikan(markdown: str, catatan: str = "", unit: str = "") -> Notula:
    """Urai Markdown notulen AI menjadi Notula; toleran terhadap susunan lama."""
    baris = markdown.replace("\r\n", "\n").split("\n")
    n = Notula(catatan=catatan, unit=unit)
    i = 0
    while i < len(baris) and not baris[i].strip():
        i += 1
    if i < len(baris) and (m := re.match(r"^#\s+(.+)$", baris[i].strip())):
        n.rapat = _bersih(re.sub(r"^notul(?:en|a|ensi)\s+(?:rapat\s+)?", "", _bersih(m.group(1)), flags=re.I))
        i += 1

    bagian: list[tuple[str, list[str]]] = []
    judul, isi = "", []
    for teks in baris[i:]:
        h2 = re.match(r"^##\s+(.+)$", teks.strip())
        if h2:
            bagian.append((judul, isi))
            judul, isi = _bersih(h2.group(1)), []
        else:
            isi.append(teks)
    bagian.append((judul, isi))

    # Butir "Label: nilai" di bawah judul (sebelum ## pertama) = keterangan kepala.
    for teks in bagian[0][1]:
        if m := re.match(r"^[-*]\s+\**([^:*\n]{2,40}?)\**\s*:\s*(.+)$", teks.strip()):
            kunci = _LABEL.get(m.group(1).strip().lower())
            if kunci == "rapat" and not n.rapat:
                n.rapat = _bersih(m.group(2))
            elif kunci:
                setattr(n, kunci, _nilai(m.group(2)))

    sisa: list[tuple[str, str]] = []
    for judul, isi in bagian[1:]:
        kunci = re.sub(r"^\d+[.)]\s*", "", judul).strip().lower()
        teks = "\n".join(isi).strip()
        if kunci == "acara":
            n.acara = _daftar(teks)
        elif kunci in ("peserta rapat", "peserta"):
            n.peserta = _daftar(teks)
        elif kunci == "kegiatan rapat":
            n.kegiatan = _pecah_kegiatan(teks)
        else:
            sisa.append((judul, teks))
    if not n.kegiatan and sisa:        # susunan lama: setiap ## menjadi satu butir kegiatan
        kegiatan: list[tuple[str, str]] = []
        for k, (j, t) in enumerate(sisa, 1):
            if j or t:
                judul_bersih = re.sub(r"^\d+[.)]\s*", "", j)
                kegiatan.append((f"{k}. {judul_bersih}", t))
        n.kegiatan = kegiatan
    return n


def _pecah_kegiatan(teks: str) -> list[tuple[str, str]]:
    """Pecah isi 'Kegiatan Rapat' pada judul ### (1. Pembukaan, 2. Pembahasan, ...)."""
    hasil: list[tuple[str, list[str]]] = []
    for baris in teks.split("\n"):
        if m := re.match(r"^###\s+(.+)$", baris.strip()):
            hasil.append((_bersih(m.group(1)), []))
        elif hasil:
            hasil[-1][1].append(baris)
        elif baris.strip():
            hasil.append(("Pembahasan", [baris]))
    keluar = []
    for urutan, (judul, isi) in enumerate(hasil, 1):
        if not re.match(r"^\d+[.)]\s", judul):
            judul = f"{urutan}. {judul}"
        keluar.append((judul, "\n".join(isi).strip()))
    return keluar


# ── Typst ────────────────────────────────────────────────────────────────
def _blok_typst(isi: str) -> str:
    keluar: list[str] = []
    for blok in urai(isi):
        if blok[0] == "judul":
            keluar.append(f"#block(above: 0.8em, below: 0.4em, sticky: true)[#strong[#{_str(blok[2])}]]")
        elif blok[0] == "paragraf":
            keluar.append(f"#{_str(blok[1])}\n#parbreak()")
        elif blok[0] in ("butir", "nomor"):
            tanda = "-" if blok[0] == "butir" else "+"
            keluar.extend(f"{tanda} #{_str(butir)}" for butir in blok[1])
            keluar.append("")
        elif blok[0] == "tabel":
            keluar.extend(_tabel_typst(blok[1]))
            keluar.append("")
    return "\n".join(keluar) or "#[]"


def _baris_isian(label: str, nilai: str) -> str:
    isi = f"#{_str(nilai)}" if nilai else "#isian"
    return f"  [{label}], [:], [{isi}],"


def _daftar_typst(butir: list[str]) -> str:
    if not butir:
        return "#isian"
    return "#enum(tight: true, indent: 0em, body-indent: 0.6em, " + ", ".join(f"[#{_str(b)}]" for b in butir) + ")"


def sumber_typst(n: Notula, logo: str = "logo-kop.png") -> str:
    baris: list[str] = [
        _baris_isian("Rapat", n.rapat),
        _baris_isian("Hari, tanggal", n.hari_tanggal),
        _baris_isian("Pukul", n.pukul),
        _baris_isian("Tempat", n.tempat),
        f"  [Acara], [:], [{_daftar_typst(n.acara)}],",
        "  [], [], [],",
        _baris_isian("Pemimpin Rapat", n.pemimpin),
        _baris_isian("Pencatat/Notulis", n.notulis),
        f"  [Peserta Rapat], [:], [{_daftar_typst(n.peserta)}],",
        "  [], [], [],",
        "  [Kegiatan Rapat], [:], [],",
    ]
    for judul, isi in n.kegiatan:
        baris.append(f"  [#h(0pt){_str_label(judul)}], [:], [{_blok_typst(isi)}],")
    return (
        TEMPLATE_PATH.read_text(encoding="utf-8")
        .replace("__KOP__", kop.typst_kop(logo, n.unit))
        .replace("__BARIS__", "\n".join(baris))
        .replace("__PEMIMPIN__", _str(n.pemimpin))
        .replace("__CATATAN__", _str(n.catatan))
    )


def _str_label(teks: str) -> str:
    return "#" + _str(teks)


def bentuk_pdf(n: Notula, keluaran: str | Path, timeout: int = 120) -> str:
    typst = shutil.which("typst")
    if not typst:
        raise PerkakasTidakTersedia("Perkakas typst tidak ada di lingkungan ini, PDF tidak dibentuk.")
    target = Path(keluaran)
    target.parent.mkdir(parents=True, exist_ok=True)
    sumber = target.with_suffix(".typ")
    logo = target.with_name(f".{target.stem}-logo.png")      # Typst hanya membaca berkas di folder proyek
    try:
        shutil.copyfile(LOGO_PATH, logo)
        sumber.write_text(sumber_typst(n, logo.name), encoding="utf-8")
        subprocess.run([typst, "compile", str(sumber), str(target)],
                       check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        rincian = (exc.stderr or exc.stdout or "compile gagal").strip()[-1200:]
        raise RuntimeError(f"Typst gagal membentuk PDF: {rincian}") from exc
    finally:
        sumber.unlink(missing_ok=True)
        logo.unlink(missing_ok=True)
    return str(target)


# ── DOCX ─────────────────────────────────────────────────────────────────
def bentuk_docx(n: Notula, keluaran: str | Path) -> str:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    from src.pandora_documents.render import LEBAR_TEKS_CM, lebar_kolom

    doc = Document()
    seksi = doc.sections[0]
    lebar_isi = kop.docx_kop(doc, seksi, n.unit)   # kop UGM, batas halaman, nomor halaman di tengah atas

    gaya = doc.styles["Normal"]
    gaya.font.name = FONT_DOCX
    gaya.font.size = Pt(12)
    gaya.element.rPr.rFonts.set(qn("w:eastAsia"), FONT_DOCX)
    gaya.paragraph_format.space_after = Pt(0)

    def jalankan(par, teks, tebal=False, ukuran=None, font=None, warna=None, miring=False):
        run = par.add_run(teks)
        run.bold, run.italic = tebal, miring
        run.font.name = font or FONT_DOCX
        run._element.rPr.rFonts.set(qn("w:eastAsia"), font or FONT_DOCX)
        if ukuran:
            run.font.size = Pt(ukuran)
        if warna is not None:
            run.font.color.rgb = warna
        return run

    def paragraf(teks="", rata=WD_ALIGN_PARAGRAPH.LEFT, tebal=False, sebelum=0, sesudah=0):
        par = doc.add_paragraph()
        par.alignment = rata
        par.paragraph_format.space_before, par.paragraph_format.space_after = Pt(sebelum), Pt(sesudah)
        if teks:
            jalankan(par, teks, tebal=tebal)
        return par

    paragraf("", sesudah=6)
    paragraf("NOTULA", rata=WD_ALIGN_PARAGRAPH.CENTER, tebal=True, sebelum=18, sesudah=18)

    # Isi: tabel tanpa garis (label | : | keterangan), seperti contoh pada lampiran.
    tabel = doc.add_table(rows=0, cols=3)
    tabel.alignment = WD_TABLE_ALIGNMENT.LEFT
    tabel.autofit = False
    lebar = (Cm(4.2), Cm(0.5), Cm(lebar_isi - 4.7))

    def baris_tabel(label, isi_fn):
        sel = tabel.add_row().cells
        for s, w in zip(sel, lebar):
            s.width = w
        if label:
            jalankan(sel[0].paragraphs[0], label)
            jalankan(sel[1].paragraphs[0], ":")
        isi_fn(sel[2])
        return sel

    def teks_atau_titik(nilai):
        return lambda sel: jalankan(sel.paragraphs[0], nilai or TITIK)

    def daftar(butir):
        def isi(sel):
            if not butir:
                jalankan(sel.paragraphs[0], TITIK)
                return
            for urutan, teks in enumerate(butir, 1):
                par = sel.paragraphs[0] if urutan == 1 else sel.add_paragraph()
                par.paragraph_format.left_indent = Cm(0.7)
                par.paragraph_format.first_line_indent = Cm(-0.7)
                jalankan(par, f"{urutan}.\t{teks}")
        return isi

    baris_tabel("Rapat", teks_atau_titik(n.rapat))
    baris_tabel("Hari, tanggal", teks_atau_titik(n.hari_tanggal))
    baris_tabel("Pukul", teks_atau_titik(n.pukul))
    baris_tabel("Tempat", teks_atau_titik(n.tempat))
    baris_tabel("Acara", daftar(n.acara))
    baris_tabel("", lambda sel: None)
    baris_tabel("Pemimpin Rapat", teks_atau_titik(n.pemimpin))
    baris_tabel("Pencatat/Notulis", teks_atau_titik(n.notulis))
    baris_tabel("Peserta Rapat", daftar(n.peserta))
    baris_tabel("", lambda sel: None)
    baris_tabel("Kegiatan Rapat", lambda sel: None)

    def isi_kegiatan(isi_md):
        def isi(sel):
            pertama = True
            for blok in urai(isi_md):
                def par_baru():
                    nonlocal pertama
                    par = sel.paragraphs[0] if pertama else sel.add_paragraph()
                    pertama = False
                    return par
                if blok[0] == "judul":
                    par = par_baru()
                    par.paragraph_format.space_before = Pt(4)
                    jalankan(par, blok[2], tebal=True)
                elif blok[0] == "paragraf":
                    par = par_baru()
                    par.paragraph_format.space_after = Pt(4)
                    jalankan(par, blok[1])
                elif blok[0] in ("butir", "nomor"):
                    for urutan, teks in enumerate(blok[1], 1):
                        par = par_baru()
                        par.paragraph_format.left_indent = Cm(0.7)
                        par.paragraph_format.first_line_indent = Cm(-0.5)
                        jalankan(par, f"{'•' if blok[0] == 'butir' else str(urutan) + '.'}\t{teks}")
                elif blok[0] == "tabel":
                    rows = blok[1]
                    tabel_dalam = sel.add_table(len(rows), len(rows[0]))
                    tabel_dalam.autofit = False
                    rencana = lebar_kolom(rows)
                    ruang = lebar_isi - 4.7
                    sisa = max(ruang - sum(v for j, v in rencana if j == "auto"), 3.0)
                    bobot = sum(v for j, v in rencana if j == "fr")
                    cm = [v if j == "auto" else (sisa * v / bobot) for j, v in rencana]
                    if not bobot:
                        cm = [ruang / len(rencana)] * len(rencana)
                    for r, (baris_t, isi_baris) in enumerate(zip(tabel_dalam.rows, rows)):
                        trpr = baris_t._tr.get_or_add_trPr()
                        trpr.append(OxmlElement("w:cantSplit"))
                        if r == 0:
                            trpr.append(OxmlElement("w:tblHeader"))
                        for s, teks, lebar_s in zip(baris_t.cells, isi_baris, cm):
                            s.width = Cm(lebar_s)
                            p = s.paragraphs[0]
                            jalankan(p, teks, tebal=(r == 0), ukuran=10.5)
                            batas = OxmlElement("w:tcBorders")
                            for sisi in ("top", "bottom"):
                                garis = OxmlElement(f"w:{sisi}")
                                garis.set(qn("w:val"), "single")
                                garis.set(qn("w:sz"), "6" if r in (0, len(rows) - 1) else "2")
                                garis.set(qn("w:color"), "000000" if r in (0, len(rows) - 1) else "AAAAAA")
                                batas.append(garis)
                            s._tc.get_or_add_tcPr().append(batas)
                    sel.add_paragraph()
                    pertama = False
        return isi

    for judul, isi_md in n.kegiatan:
        baris_tabel("", isi_kegiatan(isi_md))
        sel = tabel.rows[-1].cells
        jalankan(sel[0].paragraphs[0], judul)
        jalankan(sel[1].paragraphs[0], ":")

    # Catatan hasil AI tercetak di kaki setiap halaman (halaman pertama dan berikutnya).
    if n.catatan:
        seksi.footer_distance = Cm(1.5)
        for kaki in (seksi.first_page_footer, seksi.footer):
            par = kaki.paragraphs[0]
            par.alignment = WD_ALIGN_PARAGRAPH.LEFT
            jalankan(par, n.catatan, ukuran=9)

    # Penutup, di sisi kanan: pemimpin rapat, jabatan, ruang tanda tangan dan cap, nama, NIP/NIKA.
    jarak = paragraf("", sesudah=10)
    jarak.paragraph_format.keep_with_next = True
    for urutan, teks in enumerate(["Pemimpin Rapat", "." * 34 + ",", "", "", "",
                                   n.pemimpin or "." * 34, "NIP/NIKA " + "." * 24]):
        par = paragraf(teks)
        par.paragraph_format.left_indent = Cm(9.5)
        par.paragraph_format.keep_together = True
        if urutan < 6:
            par.paragraph_format.keep_with_next = True

    target = Path(keluaran)
    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(target))
    return str(target)
