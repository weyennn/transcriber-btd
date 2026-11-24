"""Pembentuk dokumen: naskah menjadi PDF dan DOCX bergaya naskah dinas.

PDF memakai templat Typst pada templates/naskah-dinas.typ. Templat itu tidak
mencetak keterangan alat dan tidak mencetak penanda akhir dokumen, berbeda dari
pembentuk PDF notulen yang mencetak "Dibuat oleh Mesin Transcribe · perlu
verifikasi manual" pada setiap halaman. DOCX dibentuk dengan susunan yang sama
supaya naskah yang disunting tetap sebentuk dengan yang dibagikan.

Seluruh teks naskah dikirim ke Typst sebagai string, bukan sebagai markup,
sehingga tanda seperti $, _, *, atau kurung siku di dalam naskah tidak pernah
ditafsirkan sebagai perintah tata letak.

Pembentuk PDF dijalankan sebagai proses terpisah terhadap perkakas `typst` yang
sudah ada di dalam image. Bila perkakas itu tidak tersedia, dokumen tidak
dibentuk dan pemanggil menerima penjelasan, bukan berkas yang rusak.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from dataclasses import dataclass, field

from src.pandora_documents.composer import RENCANA, Bagian, Naskah

TEMPLATE_PATH = Path(__file__).with_name("templates") / "naskah-dinas.typ"


class PerkakasTidakTersedia(RuntimeError):
    """Perkakas pembentuk PDF tidak ada di lingkungan ini."""


# ── Naskah Markdown menjadi blok ─────────────────────────────────────────
def _polos(teks: str) -> str:
    """Buang penanda penekanan Markdown; naskah dinas tidak menebalkan istilah."""
    teks = re.sub(r"\*\*(.+?)\*\*", r"\1", teks)
    teks = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"\1", teks)
    return teks.replace("`", "").strip()


def urai(markdown: str) -> list[tuple]:
    """Urai subset Markdown isi naskah menjadi blok.

    Blok: ("judul", tingkat, teks), ("paragraf", teks), ("butir", [teks]),
    ("nomor", [teks]), ("tabel", [[sel]]).
    """
    blok: list[tuple] = []
    baris = markdown.replace("\r\n", "\n").split("\n")
    paragraf: list[str] = []

    def tutup_paragraf():
        if paragraf:
            blok.append(("paragraf", _polos(" ".join(paragraf))))
            paragraf.clear()

    i = 0
    while i < len(baris):
        isi = baris[i].strip()
        if not isi or re.fullmatch(r"[-*_]{3,}", isi):
            tutup_paragraf()
            i += 1
            continue

        judul = re.match(r"^(#{1,6})\s+(.+)$", isi)
        if judul:
            tutup_paragraf()
            blok.append(("judul", len(judul.group(1)), _polos(judul.group(2))))
            i += 1
            continue

        if isi.startswith("|"):
            tutup_paragraf()
            rows: list[list[str]] = []
            while i < len(baris) and baris[i].strip().startswith("|"):
                sel = [_polos(c) for c in baris[i].strip().strip("|").split("|")]
                if sel and not all(re.fullmatch(r"[-: ]*", c) for c in sel):
                    rows.append(sel)
                i += 1
            if rows:
                kolom = max(len(r) for r in rows)
                blok.append(("tabel", [r + [""] * (kolom - len(r)) for r in rows]))
            continue

        for jenis, pola in (("butir", r"^[-*]\s+(.+)$"), ("nomor", r"^\d+[.)]\s+(.+)$")):
            if re.match(pola, isi):
                tutup_paragraf()
                butir: list[str] = []
                while i < len(baris) and (cocok := re.match(pola, baris[i].strip())):
                    butir.append(_polos(cocok.group(1)))
                    i += 1
                blok.append((jenis, butir))
                break
        else:
            paragraf.append(isi)
            i += 1
    tutup_paragraf()
    return blok


def _tempat_tanggal(kepala: dict | None) -> str:
    """Baris tempat dan tanggal di atas tanda tangan; kosong bila belum lengkap."""
    isian = kepala or {}
    tempat, tanggal = (str(isian.get(k) or "").strip() for k in ("tempat", "tanggal"))
    return f"{tempat}, {tanggal}" if tempat and tanggal else ""


# ── Typst ────────────────────────────────────────────────────────────────
def _str(teks: str) -> str:
    """Tulis teks sebagai string Typst."""
    aman = teks.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + re.sub(r"\s+", " ", aman).strip() + '"'


LEBAR_TEKS_CM = 16.0     # lebar teks A4 dengan margin 2,5 cm
BATAS_KOLOM_PENDEK = 22  # karakter; di bawah ini kolom cukup selebar isinya


def lebar_kolom(rows: list[list[str]]) -> list[tuple[str, float]]:
    """Rencana lebar kolom: ("auto", cm) untuk kolom pendek, ("fr", bobot) untuk kolom berkalimat.

    Kolom pendek (prioritas, status, tanggal) selebar isinya; kolom panjang membagi sisa
    lebar menurut panjang isinya. Tanpa kolom panjang, semua kolom berbagi lebar sama rata.
    """
    kolom = len(rows[0])
    terpanjang = [max(len(r[k]) for r in rows) for k in range(kolom)]
    kata = [max((len(w) for r in rows for w in r[k].split()), default=4) for k in range(kolom)]
    rencana: list[tuple[str, float]] = []
    for k in range(kolom):
        if terpanjang[k] <= BATAS_KOLOM_PENDEK:
            rencana.append(("auto", min(max(terpanjang[k], kata[k]) * 0.19 + 0.9, 4.2)))
        else:
            rencana.append(("fr", float(min(terpanjang[k], 60))))
    if all(jenis == "auto" for jenis, _ in rencana):
        return [("fr", 1.0)] * kolom
    return rencana


def _tabel_typst(rows: list[list[str]]) -> list[str]:
    """Tabel bergaris buku: garis di atas, di bawah kepala, tipis antarbaris, dan di bawah.

    Lebar kolom mengikuti isi; garis tipis antarbaris menjaga baris berkalimat panjang
    tetap terpisah satu sama lain.
    """
    lebar = ", ".join("auto" if jenis == "auto" else f"{nilai:g}fr" for jenis, nilai in lebar_kolom(rows))
    keluar = [
        f"#table(columns: ({lebar}), column-gutter: 4pt,",
        "  table.hline(stroke: .8pt),",
        "  table.header(" + ", ".join(f"[#{_str(c)}]" for c in rows[0]) + "),",
        "  table.hline(stroke: .5pt),",
    ]
    for urutan, baris in enumerate(rows[1:], 1):
        keluar.append("  " + ", ".join(f"[#{_str(c)}]" for c in baris) + ",")
        if urutan < len(rows) - 1:
            keluar.append("  table.hline(stroke: .25pt + luma(170)),")
    keluar.append("  table.hline(stroke: .8pt),")
    keluar.append(")")
    return keluar


def isi_ke_typst(markdown: str) -> str:
    """Konversi isi satu bagian naskah ke Typst."""
    keluar: list[str] = []
    for blok in urai(markdown):
        if blok[0] == "judul":
            keluar.append(f"=== #{_str(blok[2])}")
        elif blok[0] == "paragraf":
            keluar.append(f"#{_str(blok[1])}")
        elif blok[0] in ("butir", "nomor"):
            tanda = "-" if blok[0] == "butir" else "+"
            keluar.extend(f"{tanda} #{_str(butir)}" for butir in blok[1])
        elif blok[0] == "tabel":
            keluar.extend(_tabel_typst(blok[1]))
        keluar.append("")
    return "\n".join(keluar)


def _judul_bagian(butir) -> str:
    return f"{butir.nomor}. {butir.judul}" if butir.nomor else butir.judul


def _disorot(butir) -> bool:
    """Ringkasan eksekutif tampil menonjol di PDF maupun DOCX."""
    return butir.judul.strip().lower() in {"ringkasan eksekutif", "ringkasan"}


def sumber_typst(naskah: Naskah, kepala: dict | None = None) -> str:
    """Isi templat dengan naskah yang sudah dikonversi."""
    baris_kepala = ",\n".join(
        f"  ({_str(label)}, {_str(nilai)})" for label, nilai in naskah.kepala(kepala)
    )
    badan: list[str] = []
    for butir in naskah.bagian:
        if butir.judul:
            badan.append(f"== #{_str(_judul_bagian(butir))}")
            badan.append("")
        if _disorot(butir):
            # Ringkasan eksekutif ditonjolkan: kotak abu-abu muda bergaris tipis, tetap hitam-putih saat dicetak.
            badan.append("#block(fill: luma(240), stroke: .5pt + luma(170), inset: 10pt, radius: 2pt, width: 100%)[")
            badan.append("#set par(first-line-indent: 0em)")
            badan.append(isi_ke_typst(butir.isi))
            badan.append("]")
        else:
            badan.append(isi_ke_typst(butir.isi))
    return (
        TEMPLATE_PATH.read_text(encoding="utf-8")
        .replace("__JENIS__", _str(naskah.nama_jenis))
        .replace("__JUDUL__", _str(naskah.judul))
        .replace("__KEPALA__", baris_kepala + ("," if baris_kepala else ""))
        .replace("__CATATAN__", _str(naskah.catatan_sumber()))
        .replace("__TEMPAT_TANGGAL__", _str(_tempat_tanggal(kepala)))
        .replace("__ADA_TTD__", "true" if naskah.penanda_tangan else "false")
        .replace("__PENANDA_TANGAN__", _str(naskah.penanda_tangan or ""))
        .replace("__BODY__", "\n".join(badan))
    )


def bentuk_pdf(naskah: Naskah, keluaran: str | Path, kepala: dict | None = None,
               timeout: int = 120) -> str:
    """Bentuk PDF dari naskah. Kembalikan jalur PDF."""
    typst = shutil.which("typst")
    if not typst:
        raise PerkakasTidakTersedia(
            "Perkakas typst tidak ada di lingkungan ini, PDF tidak dibentuk."
        )
    target = Path(keluaran)
    target.parent.mkdir(parents=True, exist_ok=True)
    sumber = target.with_suffix(".typ")
    sumber.write_text(sumber_typst(naskah, kepala), encoding="utf-8")
    try:
        subprocess.run(
            [typst, "compile", str(sumber), str(target)],
            check=True, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        rincian = (exc.stderr or exc.stdout or "compile gagal").strip()[-1200:]
        raise RuntimeError(f"Typst gagal membentuk PDF: {rincian}") from exc
    finally:
        # Sumber Typst adalah berkas kerja, bukan keluaran untuk pengguna.
        sumber.unlink(missing_ok=True)
    return str(target)


# ── DOCX ─────────────────────────────────────────────────────────────────
FONT_DOCX = "Times New Roman"
TITIK_ISIAN = "." * 60


def bentuk_docx(naskah: Naskah, keluaran: str | Path, kepala: dict | None = None) -> str:
    """Bentuk DOCX dengan susunan yang sama seperti PDF. Kembalikan jalur DOCX."""
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    doc = Document()
    seksi = doc.sections[0]
    seksi.page_width, seksi.page_height = Cm(21), Cm(29.7)
    seksi.top_margin = seksi.bottom_margin = Cm(2.5)
    seksi.left_margin = seksi.right_margin = Cm(2.5)

    gaya = doc.styles["Normal"]
    gaya.font.name = FONT_DOCX
    gaya.font.size = Pt(12)
    gaya.element.rPr.rFonts.set(qn("w:eastAsia"), FONT_DOCX)

    def paragraf(teks="", rata=WD_ALIGN_PARAGRAPH.JUSTIFY, tebal=False, ukuran=None,
                 menjorok=False, sebelum=0, sesudah=6, gaya_par=None):
        par = doc.add_paragraph(style=gaya_par)
        par.alignment = rata
        fmt = par.paragraph_format
        fmt.space_before, fmt.space_after = Pt(sebelum), Pt(sesudah)
        fmt.line_spacing = 1.15
        if menjorok:
            fmt.first_line_indent = Cm(1.25)
        if teks:
            run = par.add_run(teks)
            run.bold = tebal
            run.font.name = FONT_DOCX
            if ukuran:
                run.font.size = Pt(ukuran)
        return par

    def garis_sel(sel, warna="000000", **sisi):
        batas = OxmlElement("w:tcBorders")
        for nama, tebal in sisi.items():
            garis = OxmlElement(f"w:{nama}")
            garis.set(qn("w:val"), "single")
            garis.set(qn("w:sz"), str(tebal))
            garis.set(qn("w:color"), warna)
            batas.append(garis)
        sel._tc.get_or_add_tcPr().append(batas)

    def isi_sel(sel, teks, tebal=False, rata=WD_ALIGN_PARAGRAPH.LEFT):
        par = sel.paragraphs[0]
        par.alignment = rata
        par.paragraph_format.space_after = Pt(2)
        run = par.add_run(teks)
        run.bold = tebal
        run.font.name = FONT_DOCX

    tengah = WD_ALIGN_PARAGRAPH.CENTER
    paragraf(naskah.nama_jenis.upper(), rata=tengah, tebal=True, ukuran=14, sesudah=2)
    paragraf(naskah.judul, rata=tengah, tebal=True, ukuran=12, sesudah=12)

    baris_kepala = naskah.kepala(kepala)
    if baris_kepala:
        tabel = doc.add_table(rows=len(baris_kepala), cols=3)
        tabel.autofit = False
        for baris, (label, nilai) in zip(tabel.rows, baris_kepala):
            for sel, lebar in zip(baris.cells, (Cm(4.2), Cm(0.5), Cm(11.3))):
                sel.width = lebar
            isi_sel(baris.cells[0], label)
            isi_sel(baris.cells[1], ":")
            isi_sel(baris.cells[2], nilai or TITIK_ISIAN)
        for sel in tabel.rows[-1].cells:
            garis_sel(sel, bottom=8)
        paragraf(sesudah=4)

    def sorot(par):
        """Kotak abu-abu muda bergaris tipis di sekeliling paragraf (menyatu antarparagraf)."""
        sifat = par._p.get_or_add_pPr()
        batas = OxmlElement("w:pBdr")
        for sisi in ("top", "left", "bottom", "right"):
            garis = OxmlElement(f"w:{sisi}")
            garis.set(qn("w:val"), "single")
            garis.set(qn("w:sz"), "4")
            garis.set(qn("w:space"), "6")
            garis.set(qn("w:color"), "AAAAAA")
            batas.append(garis)
        sifat.append(batas)
        isian_latar = OxmlElement("w:shd")
        isian_latar.set(qn("w:val"), "clear")
        isian_latar.set(qn("w:color"), "auto")
        isian_latar.set(qn("w:fill"), "F0F0F0")
        sifat.append(isian_latar)

    for butir in naskah.bagian:
        if butir.judul:
            par = paragraf(_judul_bagian(butir), rata=WD_ALIGN_PARAGRAPH.LEFT,
                           tebal=True, sebelum=10, sesudah=4)
            par.paragraph_format.keep_with_next = True
        awal_bagian = len(doc.paragraphs)
        for blok in urai(butir.isi):
            if blok[0] == "judul":
                par = paragraf(blok[2], rata=WD_ALIGN_PARAGRAPH.LEFT, tebal=True, sebelum=6, sesudah=3)
                par.paragraph_format.keep_with_next = True
                par.paragraph_format.left_indent = Cm(0.5)
                for run in par.runs:
                    run.italic = True      # anak judul dibedakan dari judul bagian
            elif blok[0] == "paragraf":
                paragraf(blok[1], menjorok=not _disorot(butir))
            elif blok[0] in ("butir", "nomor"):
                gaya_par = "List Bullet" if blok[0] == "butir" else "List Number"
                for urutan, teks in enumerate(blok[1], 1):
                    if blok[0] == "nomor":
                        # Penomoran ditulis langsung supaya tiap senarai mulai dari 1;
                        # gaya List Number bawaan melanjutkan hitungan antarsenarai.
                        par = paragraf(f"{urutan}.\t{teks}", sesudah=3)
                        par.paragraph_format.left_indent = Cm(1.25)
                        par.paragraph_format.first_line_indent = Cm(-0.75)
                    else:
                        paragraf(teks, sesudah=3, gaya_par=gaya_par)
            elif blok[0] == "tabel":
                rows = blok[1]
                tabel = doc.add_table(rows=len(rows), cols=len(rows[0]))
                tabel.alignment = WD_TABLE_ALIGNMENT.CENTER
                tabel.autofit = False
                rencana = lebar_kolom(rows)
                sisa = max(LEBAR_TEKS_CM - sum(n for j, n in rencana if j == "auto"), 4.0)
                bobot_fr = sum(n for j, n in rencana if j == "fr")
                lebar_sel = [Cm(n if j == "auto" else sisa * n / bobot_fr) for j, n in rencana]
                if bobot_fr == 0:     # semua kolom sama rata
                    lebar_sel = [Cm(LEBAR_TEKS_CM / len(rencana))] * len(rencana)
                for r, (baris, isi_baris) in enumerate(zip(tabel.rows, rows)):
                    sifat_baris = baris._tr.get_or_add_trPr()
                    sifat_baris.append(OxmlElement("w:cantSplit"))        # baris tidak terpotong antarhalaman
                    if r == 0:
                        sifat_baris.append(OxmlElement("w:tblHeader"))   # judul kolom diulang di halaman berikutnya
                    for sel, teks, lebar in zip(baris.cells, isi_baris, lebar_sel):
                        sel.width = lebar
                        isi_sel(sel, teks, tebal=(r == 0))
                        if r == 0:
                            garis_sel(sel, top=8, bottom=4)
                        elif r == len(rows) - 1:
                            garis_sel(sel, bottom=8)
                        else:
                            garis_sel(sel, warna="AAAAAA", bottom=2)
                paragraf(sesudah=4)
        if _disorot(butir):
            for par in doc.paragraphs[awal_bagian:]:
                sorot(par)

    paragraf(naskah.catatan_sumber(), ukuran=10, sebelum=12, sesudah=12)

    if naskah.penanda_tangan:
        tempat_tanggal = _tempat_tanggal(kepala) or "." * 34
        kiri = WD_ALIGN_PARAGRAPH.LEFT
        blok_ttd = [tempat_tanggal, f"{naskah.penanda_tangan},", "", "", "", "." * 34]
        for urutan, teks in enumerate(blok_ttd):
            par = paragraf(teks, rata=kiri, sesudah=0)
            par.paragraph_format.left_indent = Cm(9.5)
            par.paragraph_format.keep_together = True
            if urutan < len(blok_ttd) - 1:
                par.paragraph_format.keep_with_next = True

    footer = seksi.footer.paragraphs[0]
    footer.alignment = tengah
    run = footer.add_run()
    for jenis_medan, teks in (("begin", None), (None, "PAGE"), ("end", None)):
        if jenis_medan:
            medan = OxmlElement("w:fldChar")
            medan.set(qn("w:fldCharType"), jenis_medan)
        else:
            medan = OxmlElement("w:instrText")
            medan.set(qn("xml:space"), "preserve")
            medan.text = teks
        run._r.append(medan)
    run.font.name = FONT_DOCX
    run.font.size = Pt(10)

    target = Path(keluaran)
    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(target))
    return str(target)


# ── Naskah dari Markdown (notulen AI dan transkrip rapi) ──────────────────
@dataclass
class NaskahMarkdown:
    """Naskah yang bersumber dari Markdown jadi, bukan dari rencana bagian.

    Memenuhi antarmuka yang dipakai pembentuk PDF/DOCX di atas, sehingga notulen
    dan transkrip rapi dari AI memiliki tampilan yang sama dengan dokumen resmi.
    ``penanda_tangan`` bernilai None bila dokumen tidak memerlukan ruang tanda tangan.
    """

    judul: str
    nama_jenis: str
    bagian: list[Bagian]
    penanda_tangan: str | None = None
    kepala_tetap: list[tuple[str, str]] = field(default_factory=list)
    catatan: str = ""
    jenis: str = "markdown"

    def kepala(self, isian: dict | None = None) -> list[tuple[str, str]]:
        return list(self.kepala_tetap)

    def catatan_sumber(self) -> str:
        return self.catatan


_METADATA = re.compile(r"^[-*]\s+\**([^:*\n]{2,40}?)\**\s*:\s*(.+)$")
_JUDUL_BAGIAN = re.compile(r"^(\d+|[IVXLC]+)[.)]\s+(.+)$")
_AWALAN_JUDUL = re.compile(r"^(notulen(?:si)?\s+(?:rapat\s+)?|transkrip\s+rapi\s+ai\s*[—-]\s*)", re.IGNORECASE)


def naskah_dari_markdown(markdown: str, nama_jenis: str, penanda_tangan: str | None = None,
                         judul: str | None = None, kepala: list[tuple[str, str]] | None = None,
                         catatan: str = "") -> NaskahMarkdown:
    """Susun NaskahMarkdown dari Markdown notulen/transkrip hasil AI.

    - Judul memakai ``# `` pertama (awalan "Notulen Rapat" dibuang karena sudah tampil
      sebagai jenis dokumen), kecuali ``judul`` diberikan.
    - Butir ``- Label: nilai`` tepat di bawah judul menjadi kepala dokumen
      (kecuali ``kepala`` diberikan).
    - Setiap ``## `` menjadi satu bagian; angka di depannya menjadi nomor bagian.
    """
    baris = markdown.replace("\r\n", "\n").split("\n")
    i = 0
    h1 = None
    while i < len(baris) and not baris[i].strip():
        i += 1
    if i < len(baris) and (m := re.match(r"^#\s+(.+)$", baris[i].strip())):
        h1 = m.group(1).strip()
        i += 1

    ditemukan: list[tuple[str, str]] = []
    j = i
    while j < len(baris):
        isi = baris[j].strip()
        if not isi:
            j += 1
            continue
        if m := _METADATA.match(isi):
            ditemukan.append((m.group(1).strip(), re.sub(r"[*`]", "", m.group(2)).strip()))
            j += 1
            continue
        break
    if ditemukan:
        i = j

    bagian: list[Bagian] = []
    nomor, judul_bagian, isi_bagian = "", "", []

    def tutup():
        isi = "\n".join(isi_bagian).strip()
        if judul_bagian or isi:
            bagian.append(Bagian(nomor=nomor, judul=judul_bagian, petunjuk="", isi=isi))

    for isi in baris[i:]:
        if m := re.match(r"^##\s+(.+)$", isi.strip()):
            tutup()
            teks = re.sub(r"[*_`]", "", m.group(1)).strip()
            n = _JUDUL_BAGIAN.match(teks)
            nomor, judul_bagian = (n.group(1), n.group(2).strip()) if n else ("", teks)
            isi_bagian = []
        else:
            isi_bagian.append(isi)
    tutup()

    if judul is None:
        dasar = re.sub(r"[*_`]", "", h1 or "").strip()
        judul = _AWALAN_JUDUL.sub("", dasar).strip(" —-") or dasar or "Tanpa judul"
    return NaskahMarkdown(
        judul=judul, nama_jenis=nama_jenis, bagian=bagian, penanda_tangan=penanda_tangan,
        kepala_tetap=ditemukan if kepala is None else list(kepala), catatan=catatan,
    )
