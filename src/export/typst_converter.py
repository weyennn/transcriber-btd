"""Render notulen Markdown menjadi PDF dengan Typst."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


class TypstUnavailableError(RuntimeError):
    """Typst CLI tidak tersedia di environment."""


def _escape(text: str) -> str:
    """Escape karakter Typst yang bermakna pada teks biasa."""
    return text.replace("\\", "\\\\").replace("#", "\\#").replace("@", "\\@").replace("<", "\\<").replace(">", "\\>")


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
                    cells.extend(f'"{_escape(c) if c else "—"}"' for c in row + [""] * (cols - len(row)))
                output.append(f"#table(columns: {cols}, stroke: .5pt + rgb(\"777777\"), inset: 6pt, fill: (x, y) => if y == 0 {{ rgb(\"E9F3F5\") }} else {{ none }},")
                output.append("  table.header(" + ", ".join(f"[*{c}*]" for c in cells[:cols]) + "),")
                for start in range(cols, len(cells), cols):
                    output.append("  " + ", ".join(cells[start:start + cols]) + ("," if start + cols < len(cells) else ""))
                output.append(")")
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if bullet:
            output.append("- " + _inline(_escape(bullet.group(1))))
            i += 1
            continue
        numbered = re.match(r"^\d+\.\s+(.+)$", line)
        if numbered:
            output.append("+ " + _inline(_escape(numbered.group(1))))
            i += 1
            continue
        if re.fullmatch(r"[-*_]{3,}", line):
            output.append("#line(length: 100%, stroke: .7pt + gray)")
        else:
            output.append(_inline(_escape(line)))
        i += 1
    return "\n".join(output)


def _inline(text: str) -> str:
    """Pertahankan bold/italic Markdown setelah escaping karakter khusus."""
    text = re.sub(r"\*\*(.+?)\*\*", r"[*\1*]", text)
    text = re.sub(r"(?<!\*)\*(.+?)\*(?!\*)", r"[_\1_]", text)
    text = re.sub(r"`(.+?)`", r"`\1`", text)
    return text


def build_typst_source(markdown: str, title: str = "Notulen AI") -> str:
    """Buat source Typst dengan layout A4 formal dan footer halaman."""
    body = markdown_to_typst(markdown)
    return f'''#set page(paper: "a4", margin: (top: 2cm, bottom: 1.8cm, left: 2.2cm, right: 2.2cm), numbering: "1")
#set text(font: "DejaVu Serif", size: 10.5pt, lang: "id")
#set par(justify: true, leading: 0.72em, spacing: 0.75em)
#set heading(numbering: none)
#show heading.where(level: 1): set text(size: 22pt, weight: "bold", fill: rgb("1D3A4A"))
#show heading.where(level: 2): set text(size: 15pt, weight: "bold", fill: rgb("255F6B"))
#show heading.where(level: 3): set text(size: 12pt, weight: "bold", fill: rgb("39727A"))
#set list(indent: 1.1em, body-indent: .35em)
#set enum(indent: 1.1em, body-indent: .35em)
#show heading: it => {{ block(above: 1.1em, below: .45em, breakable: false, it) }}
#show link: set text(fill: rgb("255F6B"))
#align(right)[_Dibuat oleh Mesin Transcribe · perlu verifikasi manual_]
#line(length: 100%, stroke: 1.2pt + rgb("F2C84B"))

{body}

#align(center)[_Akhir Dokumen_]
'''


def render_pdf(markdown: str, output_path: str, title: str = "Notulen AI") -> str:
    """Compile Markdown notulen ke PDF dan return path output."""
    typst = shutil.which("typst")
    if not typst:
        raise TypstUnavailableError("Typst CLI tidak tersedia; PDF tidak dibuat.")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    source = target.with_suffix(".typ")
    source.write_text(build_typst_source(markdown, title), encoding="utf-8")
    try:
        subprocess.run([typst, "compile", str(source), str(target)], check=True, capture_output=True, text=True, timeout=120)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "compile gagal").strip()[-1000:]
        raise RuntimeError(f"Typst gagal membuat PDF: {detail}") from exc
    return str(target)
