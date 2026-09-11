"""Engine harus memakai HASIL_DIR dari paths.py (menghormati DATA_DIR)."""
import importlib
import os


def test_engine_hormati_data_dir(monkeypatch):
    monkeypatch.setenv("DATA_DIR", "/data")
    import src.utils.paths as paths
    importlib.reload(paths)
    import src.core.engine as engine
    importlib.reload(engine)
    assert str(engine.HASIL_DIR) == "/data/hasil"
