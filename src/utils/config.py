"""Settings persistence (AD-05 kajian) — JSON config di folder user.

Lokasi: %APPDATA%/TranscribeGUI/config.json (via platformdirs jika ada,
fallback ke Path.home()/.transcribe_gui/config.json).
Di container Docker: env `CONFIG_DIR` (→ /data/config) menimpa lokasi default.
"""

import json
import os
from pathlib import Path

_CONFIG_DIR_ENV = os.environ.get("CONFIG_DIR", "").strip()
if _CONFIG_DIR_ENV:
    _CONFIG_DIR = Path(_CONFIG_DIR_ENV)
else:
    try:
        import platformdirs
        _CONFIG_DIR = Path(platformdirs.user_config_dir("TranscribeGUI"))
    except Exception:  # noqa: BLE001
        _CONFIG_DIR = Path.home() / ".transcribe_gui"

DEFAULTS = {
    "model": "medium",
    "language": "auto",
    "device": "cpu",
    "compute_type": "int8",
    "output_dir": "",
    "with_md": False,
}


def transcription_runtime() -> dict[str, str]:
    """Runtime transkripsi dari environment deployment.

    Default CPU menjaga mode desktop/lokal lama. Container GPU menetapkan
    TRANSCRIBE_DEVICE=cuda dan TRANSCRIBE_COMPUTE_TYPE=float16.
    """
    return {
        "device": os.environ.get("TRANSCRIBE_DEVICE", DEFAULTS["device"]).strip() or DEFAULTS["device"],
        "compute_type": os.environ.get(
            "TRANSCRIBE_COMPUTE_TYPE", DEFAULTS["compute_type"]
        ).strip() or DEFAULTS["compute_type"],
    }


def _env_limit(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, "").strip() or default)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def max_concurrent_transcribe() -> int:
    """Jumlah transkripsi yang boleh berjalan bersamaan (bawaan 2)."""
    return _env_limit("MAX_CONCURRENT_TRANSCRIBE", 2, 1, 4)


def queue_limits() -> dict[str, int]:
    """Batas antrean: total yang menunggu, dan per pengguna (berjalan + menunggu)."""
    return {
        "max_waiting": _env_limit("MAX_TRANSCRIBE_QUEUE", 20, 0, 200),
        "per_user": _env_limit("MAX_TRANSCRIBE_PER_USER", 2, 1, 20),
    }


def config_path(owner_id: str | None = None) -> Path:
    if owner_id is None or owner_id == "legacy":
        return _CONFIG_DIR / "config.json"
    if not isinstance(owner_id, str) or len(owner_id) != 64 or any(c not in "0123456789abcdef" for c in owner_id):
        raise ValueError("owner_id tidak valid")
    return _CONFIG_DIR / "users" / owner_id / "settings.json"


def load_config(owner_id: str | None = None) -> dict:
    cfg = dict(DEFAULTS)
    path = config_path(owner_id)
    try:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except Exception:  # noqa: BLE001 — config corrupt → backup + reset (R-12)
        try:
            os.replace(path, path.with_suffix(".json.bak"))
        except OSError:
            pass
    return cfg


def save_config(cfg: dict, owner_id: str | None = None) -> None:
    clean = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
    path = config_path(owner_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
