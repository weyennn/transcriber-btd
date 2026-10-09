"""Render dokumen Markdown menjadi PDF dengan Typst.

Seluruh PDF resmi memakai satu template bersama, yaitu
``src/pandora_documents/templates/naskah-dinas.typ``. Template itu mencetak
halaman berkepala naskah dinas (judul jenis dokumen, judul, kepala opsional,
ruang tanda tangan) dan tidak mencetak keterangan alat maupun penanda akhir
dokumen. Dengan begitu notulen AI dan laporan berbagi tampilan yang sama.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

# Template bersama; satu sumber tampilan untuk semua PDF resmi.
TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "pandora_documents" / "templates" / "naskah-dinas.typ"


class TypstUnavailableError(RuntimeError):
    """Typst CLI tidak tersedia di environment."""


_MARKUP_SPECIALS = re.compile(r'([\\\\"#@<>$*_\[\]`~])')


def _escape(text: str) -> str:
    """Escape karakter Typst yang bermakna pada teks biasa.

    Selain #, @, dan kurung sudut, tanda $ * _ [ ] ` ~ juga bermakna di markup
    Typst; tanpa escape, kalimat biasa seperti "anggaran $5 juta" atau "3 * 4"
    membuat kompilasi PDF gagal. Dua garis miring dibaca sebagai komentar.
    """
    return _MARKUP_SPECIALS.sub(r"\\\1", text).replace("//", "\\/\\/")


def _escape_table_cell(text: str) -> str:
    """Escape text for a Typst string cell, including line breaks.

    Sel ditulis sebagai string Typst, bukan markup, jadi hanya garis miring
    terbalik dan tanda kutip yang perlu di-escape.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def markdown_to_typst(markdown: str) -> str:
    """Konversi subset Markdown notulen yang dihasilkan AI ke Typst."""
    lines = markdown.splitlines()
    output: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            output.append("")
            i += 1
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            title = _escape(re.sub(r"[*_`]", "", heading.group(2).strip()))
            if level == 1:
                output.append(f'= {title}')
            elif level == 2:
                output.append(f'== {title}')
            elif level == 3:
                output.append(f'=== {title}')
            else:
                output.append(f'==== {title}')
            i += 1
            continue
        if line.startswith("|"):
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not raw or all(re.fullmatch(r"[-: ]+", c or " ") for c in raw):
                    i += 1
                    continue
                rows.append(raw)
                i += 1
            if rows:
                cols = max(len(row) for row in rows)
                cells = []
                for row in rows:
                    cells.extend(f'"{_escape_table_cell(c) if c else "—"}"' for c in row + [""] * (cols - len(row)))
                output.append(f"#table(columns: {cols}, stroke: .5pt + rgb(\"777777\"), inset: 6pt, fill: (x, y) => if y == 0 {{ rgb(\"E9F3F5\") }} else {{ none }},")
                output.append("  table.header(" + ", ".join(cells[:cols]) + "),")
                for start in range(cols, len(cells), cols):
                    output.append("  " + ", ".join(cells[start:start + cols]) + ("," if start + cols < len(cells) else ""))
                output.append(")")
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if bullet:
            output.append("- " + _inline(bullet.group(1)))
            i += 1
            continue
        numbered = re.match(r"^\d+\.\s+(.+)$", line)
        if numbered:
            output.append("+ " + _inline(numbered.group(1)))
            i += 1
            continue
        if re.fullmatch(r"[-*_]{3,}", line):
            output.append("#line(length: 100%, stroke: .7pt + gray)")
        else:
            text = _inline(line)
            # Tanda = + / di awal baris dibaca Typst sebagai judul, senarai, atau istilah.
            output.append("\\" + text if text[:1] in "=+/" else text)
        i += 1
    return "\n".join(output)


_INLINE_MARK = re.compile(r"(\*\*.+?\*\*|(?<![\w*])\*(?!\s)[^*]+?(?<!\s)\*(?![\w*])|`[^`]+`)")


def _inline(text: str) -> str:
    """Ubah bold/italic/kode Markdown ke Typst dan escape sisa teksnya.

    Menerima teks Markdown mentah. Penanda dipisahkan lebih dulu, baru isinya
    di-escape, sehingga tanda bintang yang bukan penekanan tetap tampil apa adanya.
    """
    parts = []
    for piece in _INLINE_MARK.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            parts.append(f"#strong[{_escape(piece[2:-2])}]")
        elif piece.startswith("`") and piece.endswith("`") and len(piece) > 2:
            parts.append(f'#raw("{_escape_table_cell(piece[1:-1])}")')
        elif piece.startswith("*") and piece.endswith("*") and len(piece) > 2 and _INLINE_MARK.fullmatch(piece):
            parts.append(f"#emph[{_escape(piece[1:-1])}]")
        else:
            parts.append(_escape(piece))
    return "".join(parts)


def _typst_string(teks: str) -> str:
    """Tulis teks sebagai string Typst (aman untuk __JENIS__, __JUDUL__, dll.)."""
    aman = str(teks).replace("\\", "\\\\").replace('"', '\\"')
    return '"' + re.sub(r"\s+", " ", aman).strip() + '"'


def build_typst_source(markdown: str, title: str = "Dokumen Resmi",
                       jenis: str = "Dokumen", kepala: list[tuple[str, str]] | None = None,
                       penanda_tangan: str = "Penyusun",
                       tempat_tanggal: str = "") -> str:
    """Isi template naskah dinas bersama dengan isi Markdown.

    ``kepala`` berisi pasangan (label, nilai) untuk kepala dokumen; nilai kosong
    dicetak sebagai ruang bertitik untuk diisi tangan. Bila ``kepala`` kosong,
    blok kepala dilewati sepenuhnya.
    """
    body = markdown_to_typst(markdown)
    baris_kepala = ",\n".join(
        f"  ({_typst_string(label)}, {_typst_string(nilai)})" for label, nilai in (kepala or [])
    )
    return (
        TEMPLATE_PATH.read_text(encoding="utf-8")
        .replace("__JENIS__", _typst_string(jenis))
        .replace("__JUDUL__", _typst_string(title))
        .replace("__KEPALA__", baris_kepala + ("," if baris_kepala else ""))
        .replace("__CATATAN__", _typst_string(""))
        .replace("__TEMPAT_TANGGAL__", _typst_string(tempat_tanggal))
        .replace("__PENANDA_TANGAN__", _typst_string(penanda_tangan))
        .replace("__BODY__", body)
    )


def render_pdf(markdown: str, output_path: str, title: str = "Dokumen Resmi",
               jenis: str = "Dokumen", kepala: list[tuple[str, str]] | None = None,
               penanda_tangan: str = "Penyusun", tempat_tanggal: str = "") -> str:
    """Compile Markdown ke PDF bergaya naskah dinas dan kembalikan jalur keluaran."""
    typst = shutil.which("typst")
    if not typst:
        raise TypstUnavailableError("Typst CLI tidak tersedia; PDF tidak dibuat.")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    source = target.with_suffix(".typ")
    source.write_text(
        build_typst_source(markdown, title, jenis, kepala, penanda_tangan, tempat_tanggal),
        encoding="utf-8",
    )
    try:
        subprocess.run([typst, "compile", str(source), str(target)], check=True, capture_output=True, text=True, timeout=120)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "compile gagal").strip()[-1000:]
        raise RuntimeError(f"Typst gagal membuat PDF: {detail}") from exc
    finally:
        # Sumber Typst adalah berkas kerja, bukan keluaran untuk pengguna.
        source.unlink(missing_ok=True)
    return str(target)
