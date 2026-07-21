"""Build the standalone Sequin Windows app  ->  dist/Sequin/Sequin.exe

Rebuilds the HTML manual, then runs PyInstaller against Sequin.spec.  Run from anywhere:

    python scripts/build_exe.py

Needs PyInstaller in the environment (`pip install pyinstaller`).  The result is a onedir
build under dist/Sequin/ — zip that whole folder to share.  It ships synth-only (no sample
audio); a user adds kits via Import or by dropping a Samples/ folder next to Sequin.exe.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    # The manual is bundled into the build, so refresh it from docs/user-manual.md first.
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_manual.py")], check=True)
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(ROOT / "Sequin.spec"),
         "--noconfirm", "--clean"],
        cwd=ROOT,
    )
    if result.returncode == 0:
        # The plain-text setup readme sits beside Sequin.exe so it's the first thing a user
        # finds on opening the folder, and can never get separated from the app.
        out = ROOT / "dist" / "Sequin"
        shutil.copy2(ROOT / "packaging" / "README.txt", out / "README.txt")
        print(f"\nBuilt: {out / 'Sequin.exe'}")
        print("Zip the dist/Sequin folder to share it.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
