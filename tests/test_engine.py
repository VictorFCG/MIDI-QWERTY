"""Testes da engine com a lib `keyboard` simulada (ver tests/fakes.py).

Nada de hooks reais: as funções fake apenas registram o que foi hookado
para inspeção via KEYBOARD_HOOKS / KEYBOARD_HOTKEYS.
"""

import pytest

from fakes import KEYBOARD_HOOKS, KEYBOARD_HOTKEYS
from midi_qwerty.config import AppConfig, CCToggleAction, Mapping, NoteAction
from midi_qwerty.engine import Engine


def _cfg(toggle="scroll lock") -> AppConfig:
    return AppConfig(
        midi_port="",
        toggle_key=toggle,
        mappings=[
            Mapping(key="f1", action=CCToggleAction(channel=0, cc=20)),
            Mapping(key=toggle, action=NoteAction(channel=0, note=60)),  # colisão!
        ],
    )


@pytest.fixture()
def engine():
    e = Engine(_cfg())
    yield e
    try:
        e._shutdown_cleanup()
    except Exception:
        pass


def test_gatilho_nao_e_hookado_mesmo_sendo_mapeado(engine):
    """Colisão gatilho==mapeada (config editada à mão): o hook não pode
    engolir a tecla gatilho, senão o modo captura fica inacessível."""
    engine._apply(engine._cfg.copy())
    engine._set_capture(True)

    assert "scroll lock" not in KEYBOARD_HOOKS   # gatilho preservado
    assert "f1" in KEYBOARD_HOOKS                # mapeadas normais hookadas
    engine._set_capture(False)
    assert KEYBOARD_HOOKS == {}


def test_capture_on_off_registra_e_limpa_hooks(engine):
    cfg = AppConfig(midi_port="", toggle_key="scroll lock",
                    mappings=[Mapping(key="f1", action=CCToggleAction())])
    engine._cfg = cfg
    engine._apply(cfg.copy())

    assert "scroll lock" in KEYBOARD_HOTKEYS     # hotkey do gatilho registrada
    engine._set_capture(True)
    assert "f1" in KEYBOARD_HOOKS
    engine._set_capture(False)
    assert "f1" not in KEYBOARD_HOOKS


def test_toggle_key_vazio_nao_registra_hotkey():
    KEYBOARD_HOTKEYS.clear()
    e = Engine(AppConfig(midi_port="", toggle_key="",
                         mappings=[Mapping(key="f1", action=CCToggleAction())]))
    e._apply(e._cfg.copy())
    assert KEYBOARD_HOTKEYS == []
    try:
        e._shutdown_cleanup()
    except Exception:
        pass
