"""Locating resources whether Sequin runs from source or a frozen PyInstaller build.

Kept tiny and dependency-free so it works before wx/numpy load.  The checks are inert when
not frozen, so importing this from the shared package (FreedomHawk) changes nothing there.
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Directory of read-only bundled data (docs, etc.).  In a PyInstaller build that's
    ``sys._MEIPASS`` (the unpacked bundle); from source it's the repo root
    (``src/sequin/_bundle.py`` -> up three)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def exe_dir() -> Path:
    """The folder the app launches from — where a user can drop a ``Samples/`` folder next to
    ``Sequin.exe`` to add drum kits.  From source, the current working directory."""
    if is_frozen():
        return Path(sys.executable).parent
    return Path.cwd()
