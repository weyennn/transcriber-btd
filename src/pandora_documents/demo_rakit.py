"""Peraga penyusunan naskah dari transkrip.

Menunjukkan rencana penyusunan, cakupan sumber per bagian, dan hasil pemeriksaan
sebelum naskah dirakit menjadi dokumen. Hasilnya ditulis ke folder keluaran
supaya dapat diperiksa.

Pemakaian:

    python3 -m src.pandora_documents.demo_rakit <transkrip.txt> [--jenis notulen_rapat] [--keluaran DIR]

Dengan --tanpa-model, peraga memakai naskah tiruan untuk menguji rakitan,
gerbang, dan pembentuk berkas tanpa memanggil model.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.pandora_documents import checks, composer, model, render


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Peraga penyusunan naskah dari transkrip")
    parser.add_argument("transkrip", help="berkas transkrip.txt")
    parser.add_argument("--judul", default=None, help="judul naskah")
    parser.add_argument("--jenis", default="laporan_kegiatan",
                        choices=sorted(composer.RENCANA))
    parser.add_argument("--keluaran", default=".", help="folder keluaran naskah")
    parser.add_argument("--tanpa-model", action="store_true",
                        help="pakai naskah tiruan untuk menguji rakitan dan gerbang tanpa memanggil model")
    args = parser.parse_args(argv[1:])

    sumber_berkas = Path(args.transkrip)
    if not sumber_berkas.is_file():
        print(f"TOLAK: transkrip tidak ditemukan: {sumber_berkas}")
        return 2
    bersih = composer._bersihkan(sumber_berkas.read_text(encoding="utf-8", errors="replace"))
    judul = args.judul or sumber_berkas.stem
    rencana = composer.RENCANA[args.jenis]
    cara = "sumber penuh" if len(bersih) <= composer.BATAS_SUMBER_PENUH else "bertahap"

    print(f"Transkrip      : {sumber_berkas}")
    print(f"Panjang sumber : {len(bersih):,} karakter")
    print(f"Jenis naskah   : {rencana['nama']}")
    print(f"Jumlah bagian  : {len(rencana['bagian'])}")
    print(f"Cara susun     : {cara}")
    if cara == "bertahap":
        jendela = composer.bagi_jendela(bersih, jumlah=len(rencana["bagian"]))
        print("Rencana cakupan sumber per bagian:")
        for (nomor, nama, _), (awal, akhir) in zip(rencana["bagian"], jendela):
            print(f"  {nomor} {nama:<34} karakter {awal:>7,} sampai {akhir:>7,}")
    print()

    def tiruan(system: str, user: str) -> str:
        return ("Bagian ini disusun dari kutipan rekaman yang tersedia. "
                "Angka dan usulan yang disebut penyaji dicatat menurut urutan penyampaiannya.")

    if args.tanpa_model:
        print("Mode            : tanpa model, naskah tiruan untuk menguji rakitan dan gerbang")
    else:
        print(f"Konfigurasi AI : {model.konfigurasi()}")

    try:
        naskah = composer.rakit(bersih, judul, args.jenis,
                                tiruan if args.tanpa_model else model.panggil,
                                periksa=checks.periksa_bentuk)
    except (ConnectionError, ValueError) as exc:
        print(f"TOLAK: {exc}")
        print("Rencana di atas tetap berlaku; tidak ada naskah yang ditulis.")
        return 1

    markdown = naskah.ke_markdown()
    pelanggaran_cakupan = checks.periksa_cakupan(naskah.jejak)
    temuan_bentuk = checks.periksa_bentuk(markdown)
    pelanggaran_jejak = checks.periksa_keterlacakan(
        markdown, {"source_name": sumber_berkas.parent.name, "output_dir": str(sumber_berkas.parent)}
    )

    keluaran = Path(args.keluaran)
    keluaran.mkdir(parents=True, exist_ok=True)
    jalur_md = keluaran / "naskah.md"
    jalur_md.write_text(markdown, encoding="utf-8")

    print(f"Cara penyusunan : {naskah.jejak['cara']}")
    print(f"Sumber utuh     : {naskah.jejak['sumber_terpakai_penuh']}")
    print(f"Waktu           : {naskah.jejak['detik']} detik")
    print(f"Naskah          : {jalur_md} ({len(markdown):,} karakter)")
    print()
    print(f"Pemeriksaan cakupan : {'LULUS' if not pelanggaran_cakupan else 'TOLAK'}")
    for butir in pelanggaran_cakupan:
        print(f"  {butir}")
    print(f"Pemeriksaan bentuk  : {'LULUS' if not temuan_bentuk else f'TOLAK {len(temuan_bentuk)} penanda'}")
    for butir in temuan_bentuk[:10]:
        print(f"  baris {butir['baris']} [{butir['label']}] {butir['kutipan']!r}")
    print(f"Pemeriksaan jejak   : {'LULUS' if not pelanggaran_jejak else 'TOLAK'}")
    for butir in pelanggaran_jejak:
        print(f"  {butir}")

    gagal = bool(pelanggaran_cakupan or temuan_bentuk or pelanggaran_jejak)
    if not gagal:
        print(f"DOCX            : {render.bentuk_docx(naskah, keluaran / 'naskah.docx')}")
        try:
            print(f"PDF             : {render.bentuk_pdf(naskah, keluaran / 'naskah.pdf')}")
        except render.PerkakasTidakTersedia as exc:
            print(f"PDF             : dilewati ({exc})")
    print()
    print("HASIL: " + ("naskah ditolak, perbaiki temuan di atas" if gagal
                       else "naskah lolos seluruh pemeriksaan"))
    return 1 if gagal else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
