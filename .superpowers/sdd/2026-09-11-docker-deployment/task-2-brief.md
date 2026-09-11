### Task 2: `config.py` — CONFIG_DIR override

**Files:**
- Modify: `src/utils/config.py:11-15`
- Test: `tests/test_config.py` (baru)

**Interfaces:**
- Produces: `config_path() -> Path`, `load_config() -> dict`, `save_config(cfg: dict) -> None` — signature tidak berubah; hanya `_CONFIG_DIR` menghormati env `CONFIG_DIR`. Dipakai `server.py` via `load_config/save_config` (sudah ada).

- [ ] **Step 1: Tulis failing test**

Buat `tests/test_config.py`:

```python
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
```

- [ ] **Step 2: Jalankan test, verifikasi FAIL**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: FAIL — assertion path override (config masih pakai platformdirs/home)

- [ ] **Step 3: Implementasi**

Patch `src/utils/config.py:11-15` menjadi:

```python
_CONFIG_DIR_ENV = os.environ.get("CONFIG_DIR", "").strip()
if _CONFIG_DIR_ENV:
    _CONFIG_DIR = Path(_CONFIG_DIR_ENV)
else:
    try:
        import platformdirs
        _CONFIG_DIR = Path(platformdirs.user_config_dir("TranscribeGUI"))
    except Exception:  # noqa: BLE001
        _CONFIG_DIR = Path.home() / ".transcribe_gui"
```

Update docstring modul: tambah "Di container Docker: env `CONFIG_DIR` (→ /data/config) menimpa lokasi default."

- [ ] **Step 4: Jalankan test, verifikasi PASS**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/utils/config.py tests/test_config.py
git commit -m "feat: CONFIG_DIR env override untuk settings persistence"
```

---