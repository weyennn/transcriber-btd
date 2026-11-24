"""Uji transkripsi per potongan: audio panjang tidak dimuat utuh ke memori."""
import os
import subprocess
import types

import numpy as np
import pytest

from src.core import audio_decoder
from src.core.audio_decoder import _quiet_cut, decode_audio, iter_audio_chunks, probe_duration
from src.core.engine import CancelledError, TranscribeEngine

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "sample_audio", "sample_75s.mp3")
perlu_sampel = pytest.mark.skipif(not os.path.exists(SAMPLE), reason="sample_75s.mp3 tidak ada")


@perlu_sampel
def test_potongan_menyambung_tanpa_celah_dan_sama_dengan_dekode_utuh():
    utuh = decode_audio(SAMPLE)
    potongan = list(iter_audio_chunks(SAMPLE, chunk_seconds=20, search_seconds=5))
    assert len(potongan) >= 4
    posisi = 0.0
    for offset, sampel in potongan:
        assert offset == pytest.approx(posisi)
        assert sampel.dtype == np.float32 and len(sampel) <= 20 * 16000
        posisi += len(sampel) / 16000
    assert np.array_equal(np.concatenate([s for _, s in potongan]), utuh)
    assert posisi == pytest.approx(probe_duration(SAMPLE), abs=0.2)


@perlu_sampel
def test_rekaman_pendek_menjadi_satu_potongan():
    potongan = list(iter_audio_chunks(SAMPLE, chunk_seconds=600))
    assert len(potongan) == 1 and potongan[0][0] == 0.0


def test_titik_potong_jatuh_di_jeda_bicara():
    sr = 16000
    rng = np.random.default_rng(0)
    suara = (rng.standard_normal(20 * sr) * 8000).astype(np.int16)
    suara[int(17.0 * sr):int(18.0 * sr)] = 0  # jeda satu detik di dekat akhir
    potong = _quiet_cut(suara, sr, search_seconds=5)
    assert 17.0 * sr <= potong <= 18.0 * sr


def test_berkas_rusak_dilaporkan_bukan_dianggap_kosong(tmp_path):
    rusak = tmp_path / "rusak.mp3"
    rusak.write_bytes(b"bukan audio")
    with pytest.raises(RuntimeError, match="ffmpeg decode failed"):
        list(iter_audio_chunks(str(rusak)))
    assert probe_duration(str(rusak)) is None


class ModelTiruan:
    """Mengembalikan satu segmen per potongan dan mencatat panjang audio yang diterima."""

    def __init__(self):
        self.diterima = []

    def transcribe(self, samples, **kwargs):
        assert isinstance(samples, np.ndarray)
        self.diterima.append(len(samples) / 16000)
        nomor = len(self.diterima)
        segmen = types.SimpleNamespace(start=1.0, end=len(samples) / 16000, text=f" bagian {nomor} ")
        return iter([segmen]), types.SimpleNamespace(language="id", language_probability=0.99)


@perlu_sampel
def test_engine_menggeser_cap_waktu_dan_menggabung_hasil(tmp_path, monkeypatch):
    model = ModelTiruan()
    monkeypatch.setattr(TranscribeEngine, "load_model", classmethod(lambda cls, *a, **k: model))
    progres, log = [], []
    hasil = TranscribeEngine.transcribe(
        SAMPLE, {"output_dir": str(tmp_path), "chunk_seconds": 20},
        {"on_progress": lambda p, m: progres.append(p), "on_log": log.append})

    jumlah = len(model.diterima)
    assert jumlah >= 4 and max(model.diterima) <= 20
    assert hasil["full_text"] == " ".join(f"bagian {n}" for n in range(1, jumlah + 1))
    # Cap waktu mengikuti posisi potongan di rekaman, bukan mulai lagi dari nol.
    mentah_mulai = np.cumsum([0.0] + model.diterima[:-1]) + 1.0
    assert hasil["segments"][0]["start"] == 1.0
    assert hasil["segments"][-1]["end"] == pytest.approx(sum(model.diterima), abs=0.02)
    assert mentah_mulai[-1] > 55
    assert hasil["metadata"]["audio_duration_s"] == pytest.approx(probe_duration(SAMPLE), abs=0.2)
    assert progres == sorted(progres) and progres[-1] == 99
    assert any("diproses per potongan" in baris for baris in log)


@perlu_sampel
def test_pembatalan_menghentikan_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(TranscribeEngine, "load_model", classmethod(lambda cls, *a, **k: ModelTiruan()))
    proses = []
    popen_asli = subprocess.Popen

    def catat(*args, **kwargs):
        proses.append(popen_asli(*args, **kwargs))
        return proses[-1]

    monkeypatch.setattr(audio_decoder.subprocess, "Popen", catat)

    def batal(*args):
        raise CancelledError()

    with pytest.raises(CancelledError):
        TranscribeEngine.transcribe(SAMPLE, {"output_dir": str(tmp_path / "x"), "chunk_seconds": 20},
                                    {"on_segment": batal})
    dekoder = [p for p in proses if p.args[0] == "ffmpeg"]
    assert len(dekoder) == 1 and dekoder[0].poll() is not None
    assert not (tmp_path / "x").exists()


@perlu_sampel
def test_pembatalan_diperiksa_sebelum_model_dan_sebelum_hasil_ditulis(tmp_path, monkeypatch):
    dimuat = []
    monkeypatch.setattr(TranscribeEngine, "load_model",
                        classmethod(lambda cls, *a, **k: dimuat.append(1) or ModelTiruan()))
    with pytest.raises(CancelledError):
        TranscribeEngine.transcribe(SAMPLE, {"output_dir": str(tmp_path / "y")},
                                    {"is_cancelled": lambda: True})
    assert not (tmp_path / "y").exists()


class ModelGagalDiBagianKetiga(ModelTiruan):
    def transcribe(self, samples, **kwargs):
        if len(self.diterima) == 2:
            raise RuntimeError("CUDA out of memory")
        return super().transcribe(samples, **kwargs)


@perlu_sampel
def test_kegagalan_di_bagian_akhir_menyisakan_teks_sebagian(tmp_path, monkeypatch):
    monkeypatch.setattr(TranscribeEngine, "load_model",
                        classmethod(lambda cls, *a, **k: ModelGagalDiBagianKetiga()))
    keluar = tmp_path / "hasil"
    with pytest.raises(RuntimeError):
        TranscribeEngine.transcribe(SAMPLE, {"output_dir": str(keluar), "chunk_seconds": 20}, {})
    sebagian = (keluar / "transkrip_sebagian.txt").read_text(encoding="utf-8")
    assert "bagian 1" in sebagian and "bagian 2" in sebagian
    assert not (keluar / "transkrip.txt").exists()


@perlu_sampel
def test_progres_menyebut_nomor_bagian_dan_teks_sebagian_dibuang_saat_sukses(tmp_path, monkeypatch):
    monkeypatch.setattr(TranscribeEngine, "load_model", classmethod(lambda cls, *a, **k: ModelTiruan()))
    pesan = []
    TranscribeEngine.transcribe(SAMPLE, {"output_dir": str(tmp_path / "ok"), "chunk_seconds": 20},
                                {"on_progress": lambda p, m: pesan.append(m)})
    assert any(m.startswith("Bagian 2/") for m in pesan)
    assert (tmp_path / "ok" / "transkrip.txt").exists()
    assert not (tmp_path / "ok" / "transkrip_sebagian.txt").exists()


@perlu_sampel
def test_audio_pendek_satu_bagian_tanpa_label_dan_tanpa_berkas_sebagian(tmp_path, monkeypatch):
    monkeypatch.setattr(TranscribeEngine, "load_model", classmethod(lambda cls, *a, **k: ModelTiruan()))
    pesan = []
    TranscribeEngine.transcribe(SAMPLE, {"output_dir": str(tmp_path / "p"), "chunk_seconds": 600},
                                {"on_progress": lambda p, m: pesan.append(m)})
    assert not any(m.startswith("Bagian") for m in pesan)


@perlu_sampel
def test_lanjutkan_setelah_gagal_hanya_memproses_sisa_dan_menyambung_hasil(tmp_path, monkeypatch):
    keluar = str(tmp_path / "hasil")
    cfg = {"output_dir": keluar, "chunk_seconds": 20}
    monkeypatch.setattr(TranscribeEngine, "load_model",
                        classmethod(lambda cls, *a, **k: ModelGagalDiBagianKetiga()))
    with pytest.raises(RuntimeError):
        TranscribeEngine.transcribe(SAMPLE, cfg, {})
    assert os.path.exists(os.path.join(keluar, "transkrip_sebagian.json"))

    model = ModelTiruan()
    monkeypatch.setattr(TranscribeEngine, "load_model", classmethod(lambda cls, *a, **k: model))
    log = []
    hasil = TranscribeEngine.transcribe(SAMPLE, {**cfg, "resume": True}, {"on_log": log.append})

    penuh = sum(len(c) for _, c in iter_audio_chunks(SAMPLE, chunk_seconds=20)) / 16000
    assert sum(model.diterima) < penuh              # bagian 1-2 tidak diproses ulang
    assert any("Melanjutkan dari menit" in m for m in log)
    teks = hasil["full_text"]
    assert teks.index("bagian 1") < teks.index("bagian 2")
    starts = [s["start"] for s in hasil["segments"]]
    assert starts == sorted(starts)
    assert not os.path.exists(os.path.join(keluar, "transkrip_sebagian.json"))
    assert os.path.exists(os.path.join(keluar, "transkrip.txt"))


@perlu_sampel
def test_lanjutkan_dengan_pengaturan_berbeda_mulai_dari_awal(tmp_path, monkeypatch):
    keluar = str(tmp_path / "hasil")
    monkeypatch.setattr(TranscribeEngine, "load_model",
                        classmethod(lambda cls, *a, **k: ModelGagalDiBagianKetiga()))
    with pytest.raises(RuntimeError):
        TranscribeEngine.transcribe(SAMPLE, {"output_dir": keluar, "chunk_seconds": 20}, {})
    model = ModelTiruan()
    monkeypatch.setattr(TranscribeEngine, "load_model", classmethod(lambda cls, *a, **k: model))
    log = []
    TranscribeEngine.transcribe(SAMPLE, {"output_dir": keluar, "chunk_seconds": 25, "resume": True},
                                {"on_log": log.append})
    assert any("dimulai dari awal" in m for m in log)
    assert sum(model.diterima) == pytest.approx(
        sum(len(c) for _, c in iter_audio_chunks(SAMPLE, chunk_seconds=25)) / 16000, abs=0.1)


@perlu_sampel
def test_iter_audio_chunks_start_seconds_menggeser_offset(tmp_path):
    semua = list(iter_audio_chunks(SAMPLE, chunk_seconds=20, search_seconds=5))
    mulai = semua[1][0]
    sisa = list(iter_audio_chunks(SAMPLE, chunk_seconds=20, search_seconds=5, start_seconds=mulai))
    assert sisa[0][0] == pytest.approx(mulai, abs=0.01)
    assert sum(len(c) for _, c in sisa) / 16000 == pytest.approx(
        sum(len(c) for _, c in semua[1:]) / 16000, abs=0.2)


class ModelCatatBahasa(ModelTiruan):
    def __init__(self):
        super().__init__()
        self.bahasa = []

    def transcribe(self, samples, **kwargs):
        self.bahasa.append(kwargs.get("language"))
        segmen, info = super().transcribe(samples, **kwargs)
        return segmen, types.SimpleNamespace(language="en", language_probability=0.97)


@perlu_sampel
def test_bahasa_otomatis_dideteksi_sekali_lalu_dikunci(tmp_path, monkeypatch):
    model = ModelCatatBahasa()
    monkeypatch.setattr(TranscribeEngine, "load_model", classmethod(lambda cls, *a, **k: model))
    log = []
    hasil = TranscribeEngine.transcribe(
        SAMPLE, {"output_dir": str(tmp_path / "a"), "chunk_seconds": 20, "language": "auto"},
        {"on_log": log.append})
    assert model.bahasa[0] is None
    assert set(model.bahasa[1:]) == {"en"} and len(model.bahasa) > 1
    assert hasil["metadata"]["language"] == "en"
    assert any("Bahasa terdeteksi: en" in m for m in log)


@perlu_sampel
def test_bahasa_tetap_dipakai_apa_adanya_bila_dipilih(tmp_path, monkeypatch):
    model = ModelCatatBahasa()
    monkeypatch.setattr(TranscribeEngine, "load_model", classmethod(lambda cls, *a, **k: model))
    TranscribeEngine.transcribe(SAMPLE, {"output_dir": str(tmp_path / "b"), "chunk_seconds": 20,
                                         "language": "id"}, {})
    assert set(model.bahasa) == {"id"}
