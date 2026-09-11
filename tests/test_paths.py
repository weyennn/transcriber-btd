"""Test DATA_DIR override pada paths (Docker deployment)."""
import importlib
import os


def _reload_paths(monkeypatch, data_dir=None):
    if data_dir is None:
        monkeypatch.delenv("DATA_DIR", raising=False)
    else:
        monkeypatch.setenv("DATA_DIR", data_dir)
    import src.utils.paths as paths
    importlib.reload(paths)
    return paths


def test_default_tanpa_env(monkeypatch):
    """Tanpa DATA_DIR: perilaku lama — relatif project root."""
    paths = _reload_paths(monkeypatch)
    assert paths.HASIL_DIR == paths.PROJECT_ROOT / "transcribe_hasil"
    assert paths.UPLOAD_DIR == paths.PROJECT_ROOT / "uploads"


def test_data_dir_override(monkeypatch):
    paths = _reload_paths(monkeypatch, "/data")
    assert str(paths.HASIL_DIR) == "/data/hasil"
    assert str(paths.UPLOAD_DIR) == "/data/uploads"


def test_env_kosong_diabaikan(monkeypatch):
    """DATA_DIR string kosong = tidak diset (fallback perilaku lama)."""
    paths = _reload_paths(monkeypatch, "")
    assert paths.HASIL_DIR == paths.PROJECT_ROOT / "transcribe_hasil"
