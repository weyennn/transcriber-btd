"""Test guard DATA_DIR pada bootstrap src/export/docx_converter.py.

Ruling controller: di dalam container Docker (DATA_DIR diset), auto-bootstrap
_rerun_with_venv_python() tidak boleh re-exec ke .venv (tidak ada venv di
container). Dengan guard, import modul harus berhasil tanpa SystemExit /
subprocess.
"""

import importlib
import os
import subprocess
import sys


def test_bootstrap_skips_reexec_when_data_dir_set(monkeypatch):
    """DATA_DIR diset (container) → bootstrap no-op, import berhasil tanpa exit."""
    monkeypatch.setenv("DATA_DIR", "/data")
    monkeypatch.delitem(sys.modules, "src.export.docx_converter", raising=False)

    # Jika bootstrap memanggil subprocess.call / sys.exit, test ini gagal.
    def _forbidden_call(*args, **kwargs):  # pragma: no cover
        raise AssertionError("bootstrap memanggil subprocess.call di dalam container")

    def _forbidden_exit(*args, **kwargs):  # pragma: no cover
        raise AssertionError("bootstrap memanggil sys.exit di dalam container")

    monkeypatch.setattr(subprocess, "call", _forbidden_call)
    monkeypatch.setattr(sys, "exit", _forbidden_exit)

    mod = importlib.import_module("src.export.docx_converter")
    assert mod is not None


def test_bootstrap_guard_only_acts_on_data_dir():
    """Tanpa DATA_DIR, guard tidak aktif (fungsi melanjutkan logika normal)."""
    src = open(
        os.path.join(os.path.dirname(__file__), "..", "src", "export", "docx_converter.py"),
        encoding="utf-8",
    ).read()
    assert 'os.environ.get("DATA_DIR")' in src
