"""Pemeriksa naskah terhadap kejujuran sumber dan bentuk dokumen.

Dua pemeriksaan yang dijalankan sebelum naskah dinyatakan selesai:

1. `periksa_cakupan` memastikan seluruh transkrip benar-benar masuk ke naskah.
   Pemotongan diam-diam pada batas 180.000 karakter adalah cacat yang sudah
   terukur pada kode terpasang, dan pemeriksaan ini mencegahnya terulang.

2. `periksa_bentuk` memastikan naskah tidak memuat penanda keluaran mesin.
   Gerbang aturannya ada di pandora_quality.slop_gate, sehingga aturan bentuk
   dapat diperbaiki tanpa menyentuh berkas ini.
"""

from __future__ import annotations

import re

from src.pandora_quality.slop_gate import periksa as periksa_gaya


def periksa_cakupan(jejak: dict, panjang_sumber: int | None = None) -> list[str]:
    """Kembalikan daftar pelanggaran cakupan sumber. Daftar kosong berarti utuh.

    Bila `panjang_sumber` tidak diberikan, panjang yang dicatat pada jejak dipakai.
    Cara itu menghindari salah tuduh "sumber terpotong" hanya karena teks yang
    dihitung pemanggil sudah dirapikan spasi ujungnya.
    """
    pelanggaran: list[str] = []
    cakupan = jejak.get("cakupan") or []
    if not cakupan:
        pelanggaran.append("Jejak cakupan tidak ada, sumber tidak dapat dibuktikan utuh.")
        return pelanggaran

    acuan = panjang_sumber if panjang_sumber is not None else jejak.get("panjang_sumber")
    if acuan is None:
        pelanggaran.append("Panjang sumber tidak diketahui, cakupan tidak dapat diperiksa.")
        return pelanggaran

    if cakupan[0].get("mulai") != 0:
        pelanggaran.append(
            f"Bagian awal sumber tidak terpakai: cakupan mulai pada karakter {cakupan[0].get('mulai')}."
        )
    akhir_terjauh = max(b.get("akhir", 0) for b in cakupan)
    if akhir_terjauh != acuan:
        pelanggaran.append(
            f"Sumber terpotong: cakupan berhenti pada karakter {akhir_terjauh} "
            f"dari {acuan} karakter."
        )

    urut = sorted(cakupan, key=lambda b: b.get("mulai", 0))
    for sebelumnya, berikutnya in zip(urut, urut[1:]):
        if berikutnya.get("mulai", 0) > sebelumnya.get("akhir", 0):
            pelanggaran.append(
                f"Ada bagian sumber yang tidak terpakai antara karakter "
                f"{sebelumnya.get('akhir')} dan {berikutnya.get('mulai')}."
            )
    return pelanggaran


def periksa_bentuk(naskah: str) -> list[dict]:
    """Kembalikan daftar penanda gaya mesin pada naskah."""
    return periksa_gaya(naskah)


def _menyerupai_berkas(nilai: str | None) -> bool:
    """True bila nilai berbentuk jalur atau nama berkas, bukan sekadar nama biasa.

    Nama direktori biasa seperti "kerja" tidak boleh diperlakukan sebagai kebocoran:
    kata itu juga muncul wajar di dalam naskah ("unit kerja"). Yang benar-benar bocor
    adalah jalur dan nama berkas. Pemeriksa yang menuduh terlalu banyak akan
    diabaikan, sama tidak bergunanya dengan pemeriksa yang tidak pernah menuduh.
    """
    if not nilai:
        return False
    teks = str(nilai)
    if "/" in teks or "\\" in teks:
        return True
    return bool(re.search(r"\.(txt|json|m4a|mp3|wav|docx|pdf|md|typ|py)$", teks, re.IGNORECASE))


def periksa_keterlacakan(naskah: str, jejak: dict) -> list[str]:
    """Pastikan naskah akhir tidak memuat keterangan alat atau jalur berkas.

    Naskah yang dibagikan tidak boleh menyebut model, nama berkas audio, jalur
    direktori, atau proses penyusunannya. Keterangan itu hidup di jejak, bukan di
    dokumen pembaca.
    """
    pelanggaran: list[str] = []
    penanda = {
        "nama berkas audio": jejak.get("source_name"),
        "jalur direktori": jejak.get("output_dir"),
    }
    for label, nilai in penanda.items():
        if _menyerupai_berkas(nilai) and str(nilai) in naskah:
            pelanggaran.append(f"Naskah memuat {label}: {nilai}")
    for kata in ("transkrip.txt", "transkrip.json", "MAX_INPUT_CHARS", "typst", ".docx", ".pdf"):
        if kata in naskah:
            pelanggaran.append(f"Naskah memuat penanda berkas atau perkakas: {kata}")
    return pelanggaran
