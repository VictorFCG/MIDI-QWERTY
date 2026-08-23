@echo off
rem Gera dist\MIDI-QWERTY.exe portatil (onefile, sem console).
rem Uso no Windows, dentro da pasta do projeto:
rem   .venv\Scripts\activate
rem   pip install -e . pyinstaller
rem   build_exe.bat
setlocal
where pyinstaller >nul 2>nul
if errorlevel 1 (
  echo ERRO: pyinstaller nao encontrado. Rode: pip install pyinstaller
  exit /b 1
)
pyinstaller MIDI_QWERTY.spec --noconfirm
if errorlevel 1 (
  echo ERRO: o build falhou.
  exit /b 1
)
echo.
echo OK: dist\MIDI-QWERTY.exe
endlocal
