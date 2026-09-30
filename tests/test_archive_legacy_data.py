import importlib
import json


def _load_archive(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import src.utils.paths as paths
    importlib.reload(paths)
    import scripts.archive_legacy_data as archive
    return importlib.reload(archive)


def test_archive_legacy_data_dry_run_does_not_move(monkeypatch, tmp_path):
    archive = _load_archive(monkeypatch, tmp_path)
    legacy_result = archive.HASIL_DIR / "01_old-result"
    legacy_upload = archive.UPLOAD_DIR / "audio.bin"
    legacy_result.mkdir(parents=True)
    archive.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (legacy_result / "transkrip.txt").write_text("opaque fixture", encoding="utf-8")
    legacy_upload.write_bytes(b"opaque fixture")

    report = archive.archive()
    assert report["mode"] == "dry-run"
    assert len(report["moves"]) == 2
    assert legacy_result.exists()
    assert legacy_upload.exists()


def test_archive_skips_owner_upload_directories(monkeypatch, tmp_path):
    archive = _load_archive(monkeypatch, tmp_path)
    owner_upload = archive.UPLOAD_DIR / ("a" * 64)
    owner_upload.mkdir(parents=True)
    (owner_upload / "new-audio.m4a").write_bytes(b"fixture")
    legacy_upload = archive.UPLOAD_DIR / "legacy.m4a"
    legacy_upload.write_bytes(b"fixture")

    moves = archive.plan_moves()
    sources = {source for source, _ in moves}
    assert legacy_upload in sources
    assert owner_upload not in sources


def test_archive_legacy_data_apply_moves_directories_and_writes_rollback_manifest(monkeypatch, tmp_path):
    archive = _load_archive(monkeypatch, tmp_path)
    legacy_result = archive.HASIL_DIR / "01_old-result"
    legacy_result.mkdir(parents=True)
    (legacy_result / "transkrip.txt").write_text("opaque fixture", encoding="utf-8")

    report = archive.archive(apply=True)
    archived = archive.HASIL_DIR / "_archive_legacy" / "01_old-result"
    assert not legacy_result.exists()
    assert (archived / "transkrip.txt").exists()
    manifest = json.loads((archive.HASIL_DIR / "_archive_legacy_manifest.json").read_text())
    assert manifest["moves"][0]["destination"] == str(archived)
    assert report["manifest"] == str(archive.HASIL_DIR / "_archive_legacy_manifest.json")
