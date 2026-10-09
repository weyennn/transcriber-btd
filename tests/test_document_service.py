"""Uji pekerjaan penyusunan dokumen resmi; panggilan model diganti tiruan."""

import json
import threading

import pytest

from src.core.engine import CancelledError
from src.notulen import ai_generator
from src.pandora_documents import layanan, render

TRANSKRIP = "Rapat membahas capaian triwulan. Tim sepakat melengkapi data bulan depan."
KEPALA = {"tanggal": "Jumat, 9 Oktober 2026", "tempat": "Yogyakarta", "asing": "dibuang"}


@pytest.fixture
def hasil_folder(tmp_path):
    folder = tmp_path / "01_rapat-contoh"
    folder.mkdir()
    (folder / "transkrip.txt").write_text(TRANSKRIP, encoding="utf-8")
    return folder


@pytest.fixture
def model_bersih(monkeypatch):
    monkeypatch.setattr(ai_generator, "call_llm",
                        lambda system, user, **kw: "Pembahasan disampaikan menurut rekaman.")


def test_dokumen_tersusun_dengan_tiga_berkas_dan_jejak(hasil_folder, model_bersih, monkeypatch):
    monkeypatch.setattr(render.shutil, "which", lambda nama: None)
    peristiwa = {"progress": [], "log": [], "finished": None}
    hasil = layanan.susun_dokumen(str(hasil_folder), "laporan_kegiatan", "Rapat Contoh", KEPALA, {
        "on_progress": lambda pct, msg: peristiwa["progress"].append(pct),
        "on_log": peristiwa["log"].append,
        "on_finished": lambda r: peristiwa.update(finished=r),
    })
    assert peristiwa["finished"] == hasil
    assert peristiwa["progress"] == sorted(peristiwa["progress"]) and peristiwa["progress"][-1] == 100
    assert hasil["jenis"] == "laporan_kegiatan" and hasil["cara"] == "sumber_penuh"
    assert hasil["pdf_path"] is None  # typst tidak ada: PDF dilewati, berkas lain tetap ada
    assert any("PDF dilewati" in baris for baris in peristiwa["log"])

    markdown = (hasil_folder / "dokumen_laporan_kegiatan.md").read_text(encoding="utf-8")
    assert markdown.startswith("# Laporan Kegiatan: Rapat Contoh\n")
    assert "- Tempat: Yogyakarta" in markdown and "dibuang" not in markdown
    assert (hasil_folder / "LaporanKegiatan_rapat-contoh.docx").is_file()
    # Keterangan sumber dan model hidup di jejak, bukan di dokumen pembaca.
    assert ai_generator.AI_MODEL not in markdown and "01_rapat-contoh" not in markdown
    jejak = json.loads((hasil_folder / "dokumen_laporan_kegiatan.jejak.json").read_text(encoding="utf-8"))
    assert jejak["folder"] == "01_rapat-contoh" and jejak["model"] == ai_generator.AI_MODEL
    assert jejak["panjang_sumber"] == len(TRANSKRIP) and len(jejak["sha256_transkrip"]) == 64
    assert (hasil_folder / "transkrip.txt").read_text(encoding="utf-8") == TRANSKRIP


def test_penyusunan_ulang_tidak_menimpa_berkas_lama(hasil_folder, model_bersih, monkeypatch):
    monkeypatch.setattr(render.shutil, "which", lambda nama: None)
    layanan.susun_dokumen(str(hasil_folder), "notulen_rapat", "Versi Satu")
    layanan.susun_dokumen(str(hasil_folder), "notulen_rapat", "Versi Dua")
    assert "Versi Dua" in (hasil_folder / "dokumen_notulen_rapat.md").read_text(encoding="utf-8")
    assert "Versi Satu" in (hasil_folder / "dokumen_notulen_rapat-1.md").read_text(encoding="utf-8")
    assert (hasil_folder / "NotulenRapat_rapat-contoh-1.docx").is_file()


def test_naskah_gaya_mesin_ditolak_dan_tidak_ada_dokumen(hasil_folder, monkeypatch):
    monkeypatch.setattr(ai_generator, "call_llm",
                        lambda system, user, **kw: "Selain itu, capaian ini signifikan.")
    galat = []
    with pytest.raises(layanan.DokumenDitolak) as exc:
        layanan.susun_dokumen(str(hasil_folder), "laporan_kegiatan", "Uji", None,
                              {"on_error": galat.append})
    pesan = str(exc.value)
    assert "TOLAK Laporan Kegiatan" in pesan and "signifikan" in pesan and "perbaikan:" in pesan
    assert galat == [pesan]
    assert sorted(p.name for p in hasil_folder.iterdir()) == ["transkrip.txt"]


def test_keterangan_pengguna_ikut_diperiksa_gerbang(hasil_folder, model_bersih):
    with pytest.raises(layanan.DokumenDitolak, match="tanda pisah panjang"):
        layanan.susun_dokumen(str(hasil_folder), "laporan_kegiatan", "Rapat — Contoh")


def test_pembatalan_menghentikan_penyusunan(hasil_folder, monkeypatch):
    batal = threading.Event()
    panggilan = []

    def model(system, user, **kw):
        panggilan.append(user)
        batal.set()
        return "Pembahasan disampaikan menurut rekaman."

    monkeypatch.setattr(ai_generator, "call_llm", model)
    with pytest.raises(CancelledError):
        layanan.susun_dokumen(str(hasil_folder), "laporan_kegiatan", "Uji", None, {}, batal)
    assert len(panggilan) == 1
    assert sorted(p.name for p in hasil_folder.iterdir()) == ["transkrip.txt"]


def test_isian_dirapikan_dan_jenis_asing_ditolak(hasil_folder, model_bersih):
    assert layanan.bersihkan_isian("  Ruang\tSidang\n1 \x00 ") == "Ruang Sidang 1"
    assert len(layanan.bersihkan_isian("x" * 500)) == layanan.PANJANG_ISIAN
    with pytest.raises(ValueError, match="tidak dikenal"):
        layanan.susun_dokumen(str(hasil_folder), "surat_keputusan", "Uji")
