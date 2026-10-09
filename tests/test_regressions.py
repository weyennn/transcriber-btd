"""Uji regresi untuk bug yang ditemukan pada tinjauan 9 Oktober 2026."""
import importlib
import json
import shutil
import threading

import pytest
from fastapi import HTTPException

from src.core.engine import TranscribeEngine
from src.core.output_writer import write_json, write_txt
from src.notulen import ai_generator


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import src.utils.paths as paths
    importlib.reload(paths)
    import src.web.auth as auth
    importlib.reload(auth)
    import src.core.engine as engine
    monkeypatch.setattr(engine.TranscribeEngine, "apply_wdac_patch", classmethod(lambda cls: None))
    import src.web.server as server
    return importlib.reload(server)


USER = {"email": "local@development", "dev": True}


# ── Folder hasil ─────────────────────────────────────────────────────────
def test_folder_ke_100_tetap_terdaftar_dan_tidak_ditimpa(server):
    root = server.result_dir_for("legacy")
    for nomor in (9, 99):
        folder = root / f"{nomor:02d}_lama"
        folder.mkdir(parents=True)
        (folder / "transkrip.txt").write_text("lama", encoding="utf-8")
    ke_100 = server.Path(TranscribeEngine.reserve_folder("rapat", root))
    assert ke_100.name == "100_rapat"
    (ke_100 / "transkrip.txt").write_text("isi", encoding="utf-8")
    assert server.Path(TranscribeEngine.reserve_folder("rapat", root)).name == "101_rapat"

    # Urut menurut nomor: 100 di atas 99, dan 99 di atas 09. Folder 101 masih kosong.
    assert [item["name"] for item in server.history(USER)["items"]] == ["100_rapat", "99_lama", "09_lama"]
    assert server.history_file("100_rapat", "transkrip.txt", _user=USER)["content"] == "isi"
    assert server.delete_history("100_rapat", USER) == {"ok": True, "deleted": "100_rapat"}


def test_job_serentak_tidak_mendapat_folder_yang_sama(tmp_path):
    hasil = []
    mulai = threading.Barrier(8)

    def pesan():
        mulai.wait()
        hasil.append(TranscribeEngine.reserve_folder("rapat", tmp_path))

    pekerja = [threading.Thread(target=pesan) for _ in range(8)]
    for t in pekerja:
        t.start()
    for t in pekerja:
        t.join()
    assert len(set(hasil)) == 8
    assert sorted(p.name for p in tmp_path.iterdir()) == [f"{n:02d}_rapat" for n in range(1, 9)]


def test_job_gagal_tidak_meninggalkan_folder_kosong(server, monkeypatch, tmp_path):
    root = server.result_dir_for("legacy")
    folder = TranscribeEngine.reserve_folder("rapat", root)

    def gagal(audio_path, config, callbacks):
        callbacks["on_error"]("ffmpeg tidak ada")
        raise RuntimeError("ffmpeg tidak ada")

    monkeypatch.setattr(TranscribeEngine, "transcribe", classmethod(lambda cls, *a: gagal(*a)))
    job = server.jobs.create("audio.mp3", {"output_dir": folder})
    job.thread.join(timeout=10)
    assert job.status == "error"
    assert not server.Path(folder).exists()
    # Galat sampai ke pembaca tepat satu kali.
    galat = []
    while not job.events.empty():
        item = job.events.get()
        if item["type"] == "error":
            galat.append(item["error"])
    assert galat == ["RuntimeError: ffmpeg tidak ada"]


# ── Berkas hasil ─────────────────────────────────────────────────────────
def test_berkas_yang_belum_ada_dijawab_404(server):
    folder = server.result_dir_for("legacy") / "01_rapat"
    folder.mkdir(parents=True)
    (folder / "transkrip.txt").write_text("isi", encoding="utf-8")
    for unduh in (False, True):
        with pytest.raises(HTTPException) as exc:
            server.history_file("01_rapat", "notulen_ai.txt", download=unduh, _user=USER)
        assert exc.value.status_code == 404


# ── Stream event ─────────────────────────────────────────────────────────
def test_dua_pembaca_stream_menerima_seluruh_event(server):
    from src.web.job_manager import TranscribeJob
    job = TranscribeJob("job-sse", "x", {})
    server.jobs._register(job)
    for nomor in range(4):
        job.events.put({"type": "log", "message": str(nomor)})
    server.jobs._finish(job)

    pertama = list(server.jobs.event_stream("job-sse"))
    kedua = list(server.jobs.event_stream("job-sse"))
    assert pertama == kedua and len(pertama) == 5
    assert pertama[0].startswith("id: 1\nevent: log\n") and pertama[-1].startswith("id: 5\nevent: job_end\n")
    # Sambungan ulang melanjutkan setelah event yang sudah diterima.
    lanjutan = list(server.jobs.event_stream("job-sse", after=3))
    assert lanjutan == pertama[3:]


def test_job_selesai_yang_lama_dibuang_dari_memori(server, monkeypatch):
    from src.web import job_manager
    lama, baru = job_manager.TranscribeJob("lama", "x", {}), job_manager.TranscribeJob("baru", "x", {})
    server.jobs._register(lama)
    server.jobs._finish(lama)
    lama.finished_at -= job_manager.FINISHED_JOB_TTL_SECONDS + 1
    server.jobs._register(baru)
    assert "lama" not in server.jobs._jobs and "baru" in server.jobs._jobs


# ── PDF notulen ──────────────────────────────────────────────────────────
TEKS_RAWAN = (
    "# Notulen *rapat* [uji]\n\n"
    "Anggaran $5 juta, hitungan 3 * 4 dan 5 * 6, batas 10], berkas data_final ~ lama.\n"
    "Teks **tebal $1** dan *miring* serta `kode_x`, tautan http://ugm.ac.id//x.\n"
    "= bukan judul\n+ bukan senarai\n"
    "- butir dengan ] dan [\n\n"
    "| Prioritas | Owner |\n|---|---|\n| Tinggi $1 [x] | \"BTD\" #2 |\n"
)


def test_typst_meng_escape_tanda_markup_di_teks_biasa():
    from src.export.typst_converter import markdown_to_typst
    hasil = markdown_to_typst(TEKS_RAWAN)
    assert "Anggaran \\$5 juta, hitungan 3 \\* 4 dan 5 \\* 6, batas 10\\], berkas data\\_final \\~ lama." in hasil
    assert "#strong[tebal \\$1]" in hasil and "#emph[miring]" in hasil and '#raw("kode_x")' in hasil
    assert "http:\\/\\/ugm.ac.id\\/\\/x" in hasil
    assert "\\= bukan judul" in hasil and "\\+ bukan senarai" in hasil
    # Kepala tabel ditulis sebagai string, bukan markup berisi tanda kutip.
    assert 'table.header("Prioritas", "Owner")' in hasil
    assert '"Tinggi $1 [x]", "\\"BTD\\" #2"' in hasil


@pytest.mark.skipif(not shutil.which("typst"), reason="perkakas typst tidak tersedia")
def test_pdf_notulen_terbentuk_dari_teks_bertanda_khusus(tmp_path):
    from src.export.typst_converter import render_pdf
    render_pdf(TEKS_RAWAN, str(tmp_path / "notulen.pdf"))
    assert (tmp_path / "notulen.pdf").read_bytes().startswith(b"%PDF")


# ── AI: keluaran terpotong dan durasi audio ──────────────────────────────
class _Jawaban:
    status_code = 200
    text = ""

    def __init__(self, finish_reason):
        self._finish_reason = finish_reason

    def json(self):
        return {"choices": [{"message": {"content": "isi jawaban"}, "finish_reason": self._finish_reason}]}


class _Klien:
    def __init__(self, finish_reason):
        self._finish_reason = finish_reason

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, *args, **kwargs):
        return _Jawaban(self._finish_reason)


def test_jawaban_model_yang_terpotong_tidak_diterima(monkeypatch):
    monkeypatch.setattr(ai_generator.httpx, "Client", lambda **kw: _Klien("length"))
    with pytest.raises(ai_generator.OutputTruncatedError, match="terpotong"):
        ai_generator.call_llm("sistem", "pengguna")
    monkeypatch.setattr(ai_generator.httpx, "Client", lambda **kw: _Klien("stop"))
    assert ai_generator.call_llm("sistem", "pengguna") == "isi jawaban"


def test_transkrip_panjang_dirapikan_per_bagian_tanpa_ada_yang_hilang(tmp_path, monkeypatch):
    folder = tmp_path / "01_rapat-panjang"
    folder.mkdir()
    kalimat = [f"Kalimat nomor {n} membahas agenda rapat koordinasi." for n in range(1200)]
    transkrip = " ".join(kalimat)
    assert len(transkrip) > 4 * ai_generator.CLEANUP_CHUNK_CHARS
    (folder / "transkrip.txt").write_text(transkrip, encoding="utf-8")

    potongan = ai_generator.split_transcript(transkrip)
    assert "".join(potongan) == transkrip
    assert all(len(p) <= ai_generator.CLEANUP_CHUNK_CHARS for p in potongan)
    assert all(p.rstrip().endswith(".") for p in potongan)

    diterima = []

    def model(system, user):
        isi = user.split("=== MULAI TRANSKRIP ===\n")[1].split("\n=== AKHIR TRANSKRIP ===")[0]
        diterima.append((user, isi))
        return isi

    monkeypatch.setattr(ai_generator, "call_llm", model)
    progres = []
    ai_generator.generate_cleanup(str(folder), {"on_progress": lambda pct, msg: progres.append(pct)})
    assert len(diterima) == len(potongan) > 4
    assert f"bagian 2 dari {len(potongan)}" in diterima[1][0]
    hasil = (folder / "transkrip_rapi_ai.txt").read_text(encoding="utf-8")
    assert all(k in hasil for k in (kalimat[0], kalimat[600], kalimat[-1]))
    assert progres == sorted(progres) and progres[-1] == 100


def test_durasi_audio_sampai_ke_prompt_notulen(tmp_path):
    folder = tmp_path / "01_rapat"
    folder.mkdir()
    write_txt(str(folder), "Rapat dibuka.")
    write_json(str(folder), "a.mp3", "medium", "id", 0.99, 12.3,
               [{"start": 0.0, "end": 74.6, "text": "Rapat dibuka."}], audio_duration=75.04)
    assert json.loads((folder / "transkrip.json").read_text(encoding="utf-8"))["audio_duration_s"] == 75.0
    text, meta = ai_generator.load_transcript(str(folder))
    assert meta["audio_duration"] == 75.0
    assert "Durasi audio: 75.0 detik" in ai_generator.build_prompt(text, meta)[1]


def test_durasi_hasil_lama_diperkirakan_dari_segmen_terakhir(tmp_path):
    folder = tmp_path / "01_lama"
    folder.mkdir()
    write_txt(str(folder), "Rapat dibuka.")
    write_json(str(folder), "a.mp3", "medium", "id", 0.99, 12.3,
               [{"start": 0.0, "end": 74.6, "text": "Rapat dibuka."}])
    assert ai_generator.load_transcript(str(folder))[1]["audio_duration"] == 74.6


def test_compose_meneruskan_email_admin_ke_container():
    from pathlib import Path
    compose = (Path(__file__).parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'AUTH_ADMIN_EMAILS: "${AUTH_ADMIN_EMAILS:-}"' in compose


# ── Memori ───────────────────────────────────────────────────────────────
def test_unggahan_ditampung_di_disk_data_bukan_di_tmp(server, tmp_path, monkeypatch):
    import tempfile
    sisa = server.UPLOAD_DIR / ".tmp" / "unggahan-terputus"
    sisa.write_bytes(b"x")
    monkeypatch.setattr(tempfile, "tempdir", None)
    target = server._use_disk_backed_temp_dir()
    assert target == server.UPLOAD_DIR / ".tmp" and tempfile.gettempdir() == str(target)
    assert not sisa.exists()
    # Berkas sementara unggahan besar benar-benar jatuh di sana.
    with tempfile.SpooledTemporaryFile(max_size=4) as berkas:
        berkas.write(b"lebih dari empat byte")
        assert len(list(target.iterdir())) == 1 or berkas._rolled
    monkeypatch.delenv("DATA_DIR")
    monkeypatch.setattr(tempfile, "tempdir", None)
    assert server._use_disk_backed_temp_dir() is None and tempfile.tempdir is None


def test_hanya_satu_model_disimpan_di_memori(monkeypatch):
    import sys
    import types
    monkeypatch.setattr(TranscribeEngine, "apply_wdac_patch", classmethod(lambda cls: None))
    monkeypatch.setattr(TranscribeEngine, "_model_cache", {})
    monkeypatch.setitem(sys.modules, "faster_whisper",
                        types.SimpleNamespace(WhisperModel=lambda nama, **kw: object()))
    medium = TranscribeEngine.load_model("medium")
    assert TranscribeEngine.load_model("medium") is medium
    TranscribeEngine.load_model("small")
    assert list(TranscribeEngine._model_cache) == [("small", "cpu", "int8")]
