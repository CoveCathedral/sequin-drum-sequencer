# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for Sequin — the accessible step sequencer.

    pyinstaller Sequin.spec --noconfirm

produces  dist/Sequin/Sequin.exe  (a onedir build — zip the whole dist/Sequin folder to
share).  The build is synth-only: the built-in synth kit needs no sample files, so it stays
small and carries no third-party audio.  A user adds their own kits by Import, or by dropping
a  Samples/<KitName>/<ROLE>/*.wav  folder next to Sequin.exe.
"""
from PyInstaller.utils.hooks import collect_all

# accessible_output2 is how Sequin speaks to NVDA.  It dynamically imports its output backends
# (outputs/auto.py loads them by name) and ships the NVDA/SAPI controller DLLs in its lib/
# folder, so collect the WHOLE package — submodules, data, and binaries — or the frozen app
# would run silent for its blind user.
ao_datas, ao_binaries, ao_hidden = collect_all("accessible_output2")

datas = ao_datas + [
    ("docs/user-manual.html", "docs"),   # Help -> User Manual opens this (bundle_root()/docs)
    ("docs/user-manual.md", "docs"),
    ("docs/drum-kits.md", "docs"),
    ("LICENSE", "."),
]

a = Analysis(
    ["scripts/sequin_main.py"],
    pathex=["src"],                       # the sequin package lives under src/
    binaries=ao_binaries,
    datas=datas,
    hiddenimports=ao_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "_pytest"],   # not needed at runtime; trims size
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Sequin",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app: no flashing console window (pythonw-equivalent)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Sequin",
)
