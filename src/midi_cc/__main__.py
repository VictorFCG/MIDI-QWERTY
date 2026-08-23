"""Entry point: `midi-cc` ou `python -m midi_cc`.

Fluxo:
1. carrega (ou cria) o arquivo de configuração;
2. sobe a engine em thread própria;
3. abre a janela; ao fechar, encerra a engine limpando os hooks.

Uso:
    midi-cc [--config CAMINHO]
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import ConfigError, default, load, save
from .engine import Engine


def _load_or_create(path: str):
    try:
        return load(path)
    except FileNotFoundError:
        cfg = default()
        save(path, cfg)
        return cfg
    except ConfigError as e:
        print(f"ERRO: {path} inválido:\n  {e}\nCorrija o arquivo ou apague-o para gerar um novo.", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="midi-cc",
        description="Mapeia teclas do teclado QWERTY para comandos MIDI (via loopMIDI) com interface gráfica.",
    )
    parser.add_argument("--config", default="config.toml",
                        help="caminho do arquivo de configuração (padrão: ./config.toml)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    # Import da GUI só aqui: erros de display/dependência ficam legíveis
    from .app import MidiCCApp

    cfg = _load_or_create(args.config)
    engine = Engine(cfg)
    engine.start()
    try:
        app = MidiCCApp(engine, cfg, args.config)
        app.mainloop()
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
