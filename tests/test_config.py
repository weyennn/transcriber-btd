"""Test CONFIG_DIR override pada settings persistence (Docker deployment)."""
import importlib


def _reload_config(monkeypatch, config_dir=None):
    if config_dir is None:
        monkeypatch.delenv("CONFIG_DIR", raising=False)
    else:
        monkeypatch.setenv("CONFIG_DIR", config_dir)
    import src.utils.config as config
    importlib.reload(config)
    return config


def test_default_model_is_medium(monkeypatch):
    config = _reload_config(monkeypatch)
    assert config.DEFAULTS["model"] == "medium"


def test_config_dir_override(monkeypatch, tmp_path):
    config = _reload_config(monkeypatch, str(tmp_path))
    assert config.config_path() == tmp_path / "config.json"
    config.save_config({"model": "base", "language": "en"})
    assert (tmp_path / "config.json").is_file()
    loaded = config.load_config()
    assert loaded["model"] == "base"
    assert loaded["language"] == "en"


def test_tanpa_env_fallback(monkeypatch):
    """Tanpa CONFIG_DIR: perilaku lama (platformdirs / home)."""
    config = _reload_config(monkeypatch)
    assert "config.json" == config.config_path().name
    # tidak menyentuh disk: hanya cek path bukan di /data
    assert not str(config.config_path()).startswith("/data")
