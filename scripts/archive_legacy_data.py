"""Archive legacy shared uploads/results without opening file contents.

Dry-run is the default. Apply only after a filesystem backup and review.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
from pathlib import Path

from src.utils.paths import HASIL_DIR, UPLOAD_DIR

RESULT_RE = re.compile(r"^\d{2}_[\w\- ]+$")


def plan_moves() -> list[tuple[Path, Path]]:
    """Plan legacy numbered result folders and flat upload files only."""
    moves = []
    if HASIL_DIR.is_dir():
        for source in sorted(HASIL_DIR.iterdir()):
            if source.is_dir() and RESULT_RE.fullmatch(source.name):
                moves.append((source, HASIL_DIR / "_archive_legacy" / source.name))
    if UPLOAD_DIR.is_dir():
        for source in sorted(UPLOAD_DIR.iterdir()):
            if source.is_file() and source.name != "_archive_legacy":
                moves.append((source, UPLOAD_DIR / "_archive_legacy" / source.name))
    return moves


def archive(apply: bool = False) -> dict:
    moves = plan_moves()
    manifest_path = HASIL_DIR / "_archive_legacy_manifest.json"
    collisions = any(destination.exists() for _, destination in moves)
    if collisions or (apply and manifest_path.exists()):
        raise FileExistsError("Archive destination/manifest collision; no files moved")
    report = {
        "mode": "apply" if apply else "dry-run",
        "moves": [{"source": str(src), "destination": str(dst)} for src, dst in moves],
    }
    if not apply:
        return report

    completed = []
    try:
        for source, destination in moves:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            completed.append((source, destination))
        manifest = {
            "created_at": time.time(),
            "moves": [{"source": str(src), "destination": str(dst)} for src, dst in completed],
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
            stream.write("\n")
        os.chmod(manifest_path, 0o600)
    except Exception:
        for source, destination in reversed(completed):
            source.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                shutil.move(str(destination), str(source))
        raise
    report["manifest"] = str(manifest_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Move planned paths (otherwise dry-run)")
    args = parser.parse_args()
    print(json.dumps(archive(apply=args.apply), indent=2))


if __name__ == "__main__":
    main()
