"""Entry point: `midi-qwerty` ou `python -m midi_qwerty`.

Fluxo:
1. carrega (ou cria) o arquivo de configuração;
2. sobe a engine em thread própria;
3. abre a janela; ao fechar, encerra a engine limpando os hooks.

Uso:
    midi-qwerty [--config CAMINHO]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, default, load, save
from .engine import Engine


def _default_config_path() -> str:
    """Config padrão: ./config.toml; no exe congelado, config.toml ao lado do .exe."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve().parent / "config.toml")
    return "config.toml"


def _load_or_create(path: str):
    try:
        return load(path)
    except FileNotFoundError:
        cfg = default()
        save(path, cfg)
        return cfg
    except ConfigError as e:
        msg = (f"Arquivo de configuração inválido:\n  {path}\n\n{e}\n\n"
               "Corrija o arquivo ou apague-o para gerar um novo.")
        if getattr(sys, "frozen", False):
            try:
                import tkinter as tk
                from tkinter import messagebox

                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("MIDI-QWERTY — configuração inválida", msg)
                root.destroy()
            except Exception:
                print(f"ERRO: {msg}", file=sys.stderr)
        else:
            print(f"ERRO: {msg}", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="midi-qwerty",
        description="MIDI-QWERTY: mapeia teclas do teclado QWERTY para comandos MIDI (via loopMIDI) com interface gráfica.",
    )
    parser.add_argument("--config", default=_default_config_path(),
                        help="caminho do arquivo de configuração "
                             "(padrão: ./config.toml; no exe portátil, config.toml na pasta do .exe)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    # Import da GUI só aqui: erros de display/dependência ficam legíveis
    from .app import MidiQwertyApp

    cfg = _load_or_create(args.config)
    engine = Engine(cfg)
    engine.start()
    try:
        app = MidiQwertyApp(engine, cfg, args.config)
        app.mainloop()
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
