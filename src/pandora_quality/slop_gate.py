"""Gerbang penyajian naskah Pandora.

Menolak naskah yang masih membawa penanda keluaran mesin sebelum naskah itu dirakit
menjadi dokumen dan dibagikan. Aturan disimpan di rules.json supaya dapat diperbaiki
tanpa menyentuh kode.

Dipakai dua cara:

    from src.pandora_quality.slop_gate import periksa, laporan
    hits = periksa(teks_naskah)
    if hits:
        raise ValueError(laporan(hits))

    python3 -m src.pandora_quality.slop_gate naskah.md

Kelas temuan:
    A tipografi, B retorika, C gaya tutur, D bentuk dan penanda internal.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RULES_PATH = Path(__file__).with_name("rules.json")

_KOMPILASI = re.IGNORECASE | re.MULTILINE


def muat_aturan(path: str | Path | None = None) -> list[tuple]:
    """Baca rules.json menjadi daftar (kelas, label, pola terkompilasi, perbaikan)."""
    sumber = Path(path) if path else RULES_PATH
    data = json.loads(sumber.read_text(encoding="utf-8"))
    aturan = []
    for butir in data["rules"]:
        aturan.append((
            butir["class"],
            butir["label"],
            re.compile(butir["pattern"], _KOMPILASI),
            butir["fix"],
        ))
    return aturan


def periksa(teks: str, aturan: list[tuple] | None = None) -> list[dict]:
    """Kembalikan daftar temuan pada teks. Daftar kosong berarti naskah lolos."""
    aturan = aturan if aturan is not None else muat_aturan()
    temuan = []
    for nomor, baris in enumerate(teks.splitlines(), 1):
        for kelas, label, pola, perbaikan in aturan:
            for temuan_pola in pola.finditer(baris):
                temuan.append({
                    "kelas": kelas,
                    "label": label,
                    "baris": nomor,
                    "kutipan": temuan_pola.group(0).strip(),
                    "perbaikan": perbaikan,
                })
    return temuan


def laporan(temuan: list[dict], nama: str = "naskah") -> str:
    """Susun laporan yang dapat dibaca manusia."""
    if not temuan:
        return f"LULUS {nama}: tidak ada penanda gaya mesin."
    per_kelas: dict[str, list[dict]] = {}
    for butir in temuan:
        per_kelas.setdefault(butir["kelas"], []).append(butir)
    baris = [f"TOLAK {nama}: {len(temuan)} penanda gaya mesin."]
    for kelas in sorted(per_kelas):
        baris.append(f"kelas {kelas}: {len(per_kelas[kelas])} temuan")
        for butir in per_kelas[kelas]:
            baris.append(
                f"  baris {butir['baris']} [{butir['label']}] {butir['kutipan']!r}"
            )
            baris.append(f"    perbaikan: {butir['perbaikan']}")
    return "\n".join(baris)


def periksa_berkas(path: str | Path) -> tuple[list[dict], str]:
    """Periksa satu berkas teks atau markdown."""
    berkas = Path(path)
    if not berkas.is_file():
        raise FileNotFoundError(berkas)
    teks = berkas.read_text(encoding="utf-8", errors="replace")
    return periksa(teks), berkas.name


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    temuan, nama = periksa_berkas(argv[1])
    print(laporan(temuan, nama))
    return 1 if temuan else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
