# -*- mode: python ; coding: utf-8 -*-
"""MIDI_QWERTY.spec — gera dist/MIDI-QWERTY.exe portável (onefile, sem console).

Uso no Windows, dentro do venv do projeto:
    pip install -e . pyinstaller
    pyinstaller MIDI_QWERTY.spec --noconfirm
    (ou simplesmente rode build_exe.bat)

Notas de empacotamento:
    * collect_data_files("customtkinter"): temas/assets não são autodetectados.
    * hiddenimports mido.backends.rtmidi/rtmidi: backend carregado via string
      em midi.py (`mido.set_backend("mido.backends.rtmidi")`).
    * upx desligado: reduz falso positivo de antivírus com onefile.
"""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("customtkinter")

a = Analysis(
    ["run.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "customtkinter",
        "keyboard",
        "keyboard._winkeyboard",
        "keyboard._nixkeyboard",
        "mido",
        "mido.backends.rtmidi",
        "rtmidi",
        "python_rtmidi",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MIDI-QWERTY",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
