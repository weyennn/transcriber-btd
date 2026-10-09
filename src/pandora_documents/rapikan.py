"""Perapian tipografi naskah sebelum gerbang penyajian.

Yang dirapikan di sini hanya bentuk penulisan yang dapat diperbaiki secara
mekanis tanpa menyentuh isi: tanda pisah panjang, tanda kutip melengkung,
penanda penebalan, dan tingkat judul. Temuan retorika dan gaya tutur tidak
diperbaiki di sini; bagian itu ditulis ulang oleh model atau ditolak gerbang.
"""

from __future__ import annotations

import re

_KUTIP = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})


def rapikan_isi(teks: str) -> str:
    """Rapikan tipografi isi satu bagian naskah."""
    teks = teks.replace("\r\n", "\n").translate(_KUTIP)

    # Rentang angka memakai tanda hubung; tanda pisah di antara kata menjadi koma.
    teks = re.sub(r"(?<=\d)\s*[–—]\s*(?=\d)", "-", teks)
    teks = re.sub(r"\s*[–—]\s*", ", ", teks)

    baris_keluar: list[str] = []
    for baris in teks.split("\n"):
        # Senarai bertanda bintang disamakan dengan tanda hubung lebih dulu,
        # supaya bintangnya tidak terbaca sebagai penanda penekanan.
        baris = re.sub(r"^(\s*)\*\s+", r"\1- ", baris)
        baris = re.sub(r"\*\*(.+?)\*\*", r"\1", baris)
        baris = re.sub(r"__(.+?)__", r"\1", baris)
        baris = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"\1", baris)
        baris = baris.replace("**", "")
        # Judul bagian milik penyusun. Judul dari model diturunkan menjadi subjudul.
        baris = re.sub(r"^\s*#{1,6}\s+", "### ", baris)
        baris_keluar.append(baris.rstrip())

    teks = "\n".join(baris_keluar)
    teks = re.sub(r"[ \t]{2,}", " ", teks)
    return re.sub(r"\n{3,}", "\n\n", teks).strip()
