"""Testes da engine com a lib `keyboard` simulada.

O módulo fake é injetado ANTES do import de `midi_qwerty.engine`, que faz
`import keyboard` no escopo global. Nada de hooks reais: as funções fake
apenas registram o que foi hookado para inspeção.
"""

import sys
import types

_hooks: dict[str, object] = {}
_hotkeys: list[str] = []


def _install_fake_keyboard() -> None:
    fake = types.ModuleType("keyboard")

    def hook_key(key, callback, suppress=False):
        _hooks[key] = callback
        return key

    def unhook_key(key):
        _hooks.pop(key, None)

    def add_hotkey(key, callback, **kwargs):
        _hotkeys.append(key)
        return f"hotkey:{key}"

    def remove_hotkey(handle):
        k = str(handle).removeprefix("hotkey:")
        if k in _hotkeys:
            _hotkeys.remove(k)

    fake.hook_key = hook_key
    fake.unhook_key = unhook_key
    fake.add_hotkey = add_hotkey
    fake.remove_hotkey = remove_hotkey
    sys.modules["keyboard"] = fake


_install_fake_keyboard()

from midi_qwerty.config import AppConfig, Mapping, CCToggleAction, NoteAction  # noqa: E402
from midi_qwerty.engine import Engine  # noqa: E402

import pytest  # noqa: E402


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
    _hooks.clear()
    _hotkeys.clear()
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

    assert "scroll lock" not in _hooks      # gatilho preservado
    assert "f1" in _hooks                   # mapeadas normais hookadas
    engine._set_capture(False)
    assert _hooks == {}


def test_capture_on_off_registra_e_limpa_hooks(engine):
    cfg = AppConfig(midi_port="", toggle_key="scroll lock",
                    mappings=[Mapping(key="f1", action=CCToggleAction())])
    engine._cfg = cfg
    engine._apply(cfg.copy())

    assert "scroll lock" in _hotkeys        # hotkey do gatilho registrada
    engine._set_capture(True)
    assert "f1" in _hooks
    engine._set_capture(False)
    assert "f1" not in _hooks


def test_toggle_key_vazio_nao_registra_hotkey():
    _hotkeys.clear()
    e = Engine(AppConfig(midi_port="", toggle_key="",
                         mappings=[Mapping(key="f1", action=CCToggleAction())]))
    e._apply(e._cfg.copy())
    assert _hotkeys == []
    try:
        e._shutdown_cleanup()
    except Exception:
        pass
