"""Uji gerbang penyajian naskah.

Kontrol negatif wajib ada: gerbang yang tidak pernah menolak apa pun tidak dapat
dibedakan dari gerbang yang tidak ada. Berkas naskah_contoh_gagal.md adalah naskah
gaya mesin yang harus tetap ditolak.
"""

from pathlib import Path

import pytest

from src.pandora_quality.slop_gate import laporan, muat_aturan, periksa

CONTOH = Path(__file__).parent / "naskah_contoh_gagal.md"


def test_naskah_bersih_lolos():
    naskah = (
        "## I Dasar Pelaksanaan\n"
        "Kegiatan dilaksanakan berdasarkan permintaan pimpinan unit pada rapat 7 Oktober 2026.\n"
    )
    assert periksa(naskah) == []


@pytest.mark.parametrize("cuplikan,kelas", [
    ("Pencapaian naik \u2014 dari 57 persen.", "A"),
    ("Dokumen ini memakai tanda kutip \u201cmelengkung\u201d.", "A"),
    ("Indikator **TCK 27** belum tercapai.", "A"),
    ("Selain itu, panitia menyampaikan hasil.", "B"),
    ("Perlu dicatat bahwa data belum lengkap.", "B"),
    ("Sistem ini robust dan seamless.", "B"),
    ("Perbaikan ini signifikan bagi unit kerja.", "B"),
    ("Secara keseluruhan, kegiatan berjalan baik.", "C"),
    ("Bagaimana jika data itu tidak tersedia?", "C"),
    ("Berkas hasil ekstraksi mesin disimpan di server.", "D"),
    ("Dokumen ini hanya-baca dan tidak boleh dibagikan.", "D"),
    ("Dibuat oleh Mesin Transcribe, perlu verifikasi manual.", "D"),
])
def test_gerbang_menolak(cuplikan, kelas):
    temuan = periksa(cuplikan)
    assert temuan, f"gerbang meloloskan: {cuplikan!r}"
    assert kelas in {t["kelas"] for t in temuan}


def test_kontrol_negatif_berkas_contoh_tetap_ditolak():
    assert CONTOH.is_file(), "berkas kontrol negatif hilang"
    temuan = periksa(CONTOH.read_text(encoding="utf-8"))
    assert len(temuan) >= 10, "kontrol negatif tidak lagi ditolak dengan cukup"


def test_aturan_terbaca_dan_berkelas():
    aturan = muat_aturan()
    assert len(aturan) >= 10
    assert {k for k, _, _, _ in aturan} == {"A", "B", "C", "D"}


def test_laporan_memuat_perbaikan():
    teks = laporan(periksa("Pencapaian naik \u2014 tajam."))
    assert "perbaikan:" in teks
