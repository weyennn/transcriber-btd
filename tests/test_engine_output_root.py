from pathlib import Path

from src.core.engine import TranscribeEngine


def test_auto_folder_uses_explicit_owner_root(tmp_path):
    owner_root = tmp_path / "owner-a" / "hasil"
    first = Path(TranscribeEngine.auto_folder("recording", owner_root))
    assert first.parent == owner_root
    assert first.name == "01_recording"
    first.mkdir(parents=True)
    second = Path(TranscribeEngine.auto_folder("recording", owner_root))
    assert second == owner_root / "02_recording"
