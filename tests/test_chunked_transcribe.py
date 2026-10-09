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
