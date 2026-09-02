import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import fakes  # noqa: E402

fakes.install()  # precisa rodar antes do primeiro import de midi_qwerty.*

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_recorders():
    fakes.KEYBOARD_HOOKS.clear()
    fakes.KEYBOARD_HOTKEYS.clear()
    fakes.WIDGET_KWARGS.clear()
    yield


@pytest.fixture()
def app_factory(tmp_path):
    """Constrói MidiQwertyApp headless com a config TOML fornecida."""
    from midi_qwerty.app import MidiQwertyApp
    from midi_qwerty.config import loads
    from midi_qwerty.engine import Engine

    def _make(toml_text: str) -> MidiQwertyApp:
        cfg = loads(toml_text)
        path = tmp_path / "config.toml"
        path.write_text(toml_text, encoding="utf-8")
        return MidiQwertyApp(Engine(cfg), cfg, str(path))

    return _make
