"""Launcher usado pelo PyInstaller (ver midi_qwerty.spec / build_exe.bat).

Em dev: `python run.py` (o caminho src/ é resolvido abaixo) ou
`PYTHONPATH=src python -m midi_qwerty`.
"""
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from midi_qwerty.__main__ import main

if __name__ == "__main__":
    main()
