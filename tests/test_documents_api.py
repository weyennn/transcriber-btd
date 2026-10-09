"""Uji titik akhir dokumen resmi: batas akses, validasi, dan isolasi antar pengguna."""
import importlib

import pytest
from fastapi import HTTPException


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
    server = importlib.reload(server)
    dibuat = []

    class JobTiruan:
        def to_dict(self):
            return {"id": "job-1", "kind": "ai_document"}

    def create_document(output_dir, **kw):
        dibuat.append((output_dir, kw))
        return JobTiruan()

    monkeypatch.setattr(server.jobs, "create_document", create_document)
    server.dibuat = dibuat
    return server


ALICE = {"sub": "alice", "email": "alice@example.test"}
BOB = {"sub": "bob", "email": "bob@example.test"}


def _folder(server, user, nama):
    folder = server.result_dir_for(server._owner_id(user)) / nama
    folder.mkdir(parents=True)
    (folder / "transkrip.txt").write_text("isi", encoding="utf-8")
    return folder


def test_jenis_dokumen_dan_isian_kepala_tersedia(server):
    items = server.document_types(ALICE)["items"]
    assert [item["jenis"] for item in items] == ["laporan_kegiatan", "notulen_rapat"]
    assert {"kunci": "tanggal", "label": "Hari, tanggal"} in items[0]["kepala"]


def test_dokumen_dimulai_untuk_folder_milik_sendiri(server):
    folder = _folder(server, ALICE, "01_rapat")
    hasil = server.document_generate({
        "folder_name": "01_rapat", "jenis": "notulen_rapat", "judul": "  Rapat\nKoordinasi ",
        "kepala": {"tempat": "Ruang Sidang", "nomor_surat": "001/UN1"},
    }, ALICE)
    assert hasil == {"id": "job-1", "kind": "ai_document"}
    output_dir, kw = server.dibuat[0]
    assert output_dir == str(folder)
    assert kw["jenis"] == "notulen_rapat" and kw["judul"] == "Rapat Koordinasi"
    assert kw["owner_id"] == server._owner_id(ALICE)
    # Hanya isian kepala yang dikenal jenisnya yang diteruskan; nomor surat tidak pernah.
    assert kw["kepala"] == {"tanggal": "", "waktu": "", "tempat": "Ruang Sidang",
                            "pimpinan": "", "notulis": ""}


def test_pengguna_lain_tidak_dapat_menyusun_dari_folder_orang(server):
    _folder(server, BOB, "01_bob")
    with pytest.raises(HTTPException) as exc:
        server.document_generate({"folder_name": "01_bob"}, ALICE)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as tidak_ada:
        server.document_generate({"folder_name": "01_tidak-ada"}, ALICE)
    # Pesan tidak membedakan antara tidak ada dan bukan milik Anda.
    assert tidak_ada.value.detail == exc.value.detail
    with pytest.raises(HTTPException) as jalur:
        server.document_generate({"folder_name": f"../{server._owner_id(BOB)}/01_bob"}, ALICE)
    assert jalur.value.status_code == 404
    assert server.dibuat == []


def test_masukan_tidak_sah_ditolak(server):
    _folder(server, ALICE, "01_rapat")
    for body, kode in (({}, 400), ({"folder_name": "01_rapat", "jenis": "surat_keputusan"}, 400),
                       ({"folder_name": "bukan folder hasil"}, 400)):
        with pytest.raises(HTTPException) as exc:
            server.document_generate(body, ALICE)
        assert exc.value.status_code == kode
    assert server.dibuat == []


def test_dokumen_dimatikan_bersama_fitur_ai(server, monkeypatch):
    _folder(server, ALICE, "01_rapat")
    monkeypatch.setattr(server, "AI_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        server.document_generate({"folder_name": "01_rapat"}, ALICE)
    assert exc.value.status_code == 503


def test_riwayat_menampilkan_naskah_dokumen_tetapi_bukan_arsipnya(server):
    folder = _folder(server, ALICE, "01_rapat")
    for nama in ("dokumen_laporan_kegiatan.md", "dokumen_laporan_kegiatan-1.md", "catatan.md"):
        (folder / nama).write_text("x", encoding="utf-8")
    files = server.history(ALICE)["items"][0]["files"]
    assert files == ["dokumen_laporan_kegiatan.md", "transkrip.txt"]


def test_job_dokumen_berjalan_sampai_selesai(server, monkeypatch, tmp_path):
    """Jalur JobManager asli: pekerjaan berlatar, progres, lalu berkas di folder hasil."""
    import time
    from src.notulen import ai_generator
    from src.pandora_documents import render
    from src.web.job_manager import JobManager
    monkeypatch.setattr(ai_generator, "call_llm",
                        lambda system, user, **kw: "Pembahasan disampaikan menurut rekaman.")
    monkeypatch.setattr(render.shutil, "which", lambda nama: None)
    folder = _folder(server, ALICE, "01_rapat")
    manager = JobManager()
    job = manager.create_document(str(folder), jenis="laporan_kegiatan", judul="Rapat",
                                  kepala={"tempat": "Yogyakarta"}, owner_id="legacy")
    job.thread.join(timeout=20)
    assert job.status == "done", job.error
    assert job.kind == "ai_document" and job.to_dict()["output_dir"] == "01_rapat"
    peristiwa = []
    while not job.events.empty():
        peristiwa.append(job.events.get()["type"])
    assert peristiwa[-2:] == ["finished", "job_end"] and "progress" in peristiwa
    assert (folder / "dokumen_laporan_kegiatan.md").is_file()
