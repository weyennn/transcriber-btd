"""Retensi hasil 30 hari: yang kedaluwarsa dihapus, yang lain tidak disentuh."""

import os
import time

import pytest

from src.utils import paths, retention


def _folder(root, name, age_days, content="x"):
    folder = root / name
    folder.mkdir(parents=True)
    berkas = folder / "transkrip.txt"
    berkas.write_text(content)
    past = time.time() - age_days * 86400
    os.utime(berkas, (past, past)); os.utime(folder, (past, past))
    return folder


@pytest.fixture
def hasil(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "HASIL_DIR", tmp_path / "hasil")
    (tmp_path / "hasil").mkdir()
    return tmp_path / "hasil"


def test_expired_result_folders_are_removed_including_owner_namespaces(hasil):
    owner = hasil / ("a" * 64)
    lama_legacy = _folder(hasil, "01_lama", 40)
    baru_legacy = _folder(hasil, "02_baru", 5)
    lama_owner = _folder(owner, "01_lama", 31)
    baru_owner = _folder(owner, "02_baru", 29)

    dihapus = retention.purge_expired_results(30)

    assert set(dihapus) == {str(lama_legacy), str(lama_owner)}
    assert not lama_legacy.exists() and not lama_owner.exists()
    assert baru_legacy.exists() and baru_owner.exists()


def test_folder_with_a_recent_file_inside_is_kept(hasil):
    folder = _folder(hasil, "01_aktif", 40)
    (folder / "notulen_ai.md").write_text("baru")   # diubah baru saja
    assert retention.purge_expired_results(30) == []
    assert folder.exists()


def test_other_folders_and_symlinks_are_never_touched(hasil, tmp_path):
    arsip = _folder(hasil, "_archive_legacy", 400)
    bebas = _folder(hasil, "catatan", 400)
    korban = tmp_path / "di-luar"
    korban.mkdir(); (korban / "penting.txt").write_text("jangan hapus")
    (hasil / "03_tautan").symlink_to(korban, target_is_directory=True)

    retention.purge_expired_results(30)

    assert arsip.exists() and bebas.exists()
    assert (korban / "penting.txt").exists()


def test_dry_run_and_disabled_do_not_delete(hasil):
    lama = _folder(hasil, "01_lama", 90)
    assert retention.purge_expired_results(30, dry_run=True) == [str(lama)]
    assert lama.exists()
    assert retention.purge_expired_results(0) == []
    assert lama.exists()


def test_retention_days_reads_env_with_safe_defaults(monkeypatch):
    monkeypatch.delenv("RESULT_RETENTION_DAYS", raising=False)
    monkeypatch.setenv("DATA_DIR", "/data")
    assert retention.retention_days() == 30
    monkeypatch.delenv("DATA_DIR")
    assert retention.retention_days() == 0          # lokal: tidak menghapus apa pun
    monkeypatch.setenv("DATA_DIR", "/data")
    for nilai, harapan in (("14", 14), ("0", 0), ("-3", 0), ("abc", 30), ("", 30)):
        monkeypatch.setenv("RESULT_RETENTION_DAYS", nilai)
        assert retention.retention_days() == harapan


def test_old_finished_job_rows_are_purged_but_active_ones_kept(tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    from src.web import job_store as store
    store = importlib.reload(store)
    store.init()

    class J:
        kind, audio_path, config, status = "transcribe", "/x.mp3", {}, "pending"
        def __init__(self, id): self.id = id

    for id_, status in (("lama-selesai", "done"), ("lama-gagal", "error"), ("lama-jalan", "running")):
        store.create(J(id_)); store.update(J(id_), status=status)
    with store._connect() as c:
        c.execute("UPDATE jobs SET updated_at=?", (time.time() - 40 * 86400,))
    store.create(J("baru")); store.update(J("baru"), status="done")

    assert store.purge_finished_before(time.time() - 30 * 86400) == 2
    assert store.get("lama-jalan") and store.get("baru")
    assert store.get("lama-selesai") is None


def test_ui_discloses_storage_retention_and_ai_data_flow():
    from pathlib import Path
    root = Path(__file__).parents[1] / "src" / "web"
    html = (root / "templates" / "index.html").read_text(encoding="utf-8")
    js = (root / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="data-notice"' in html and "dihapus dari server setelah transkripsi selesai" in html
    assert "layanan model bahasa" in html
    assert "env.retention_days" in js
