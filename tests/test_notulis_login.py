"""Nama pencatat notula berasal dari akun Google yang login."""

from src.pandora_documents import notula as render_notula


def test_uraikan_default_notulis_kosong_dan_bisa_ditimpa():
    md = "# Notulen Rapat Uji\n\n## Kegiatan Rapat\n1. Pembukaan\n   - Rapat dibuka.\n"
    n = render_notula.uraikan(md)
    assert n.notulis == ""
    n.notulis = "Budi Santoso"
    assert n.notulis == "Budi Santoso"


def test_nama_pencatat_dari_session(monkeypatch):
    from src.web.identitas import nama_pencatat
    assert nama_pencatat({"dev": True, "name": "X"}) == ""
    assert nama_pencatat({"name": "Budi Santoso", "email": "b@ugm.ac.id"}) == "Budi Santoso"
    assert nama_pencatat({"name": "", "email": "budi@ugm.ac.id"}) == "budi"
    assert nama_pencatat({"name": "", "email": ""}) == ""
