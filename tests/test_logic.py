"""Testes da lógica pura: config TOML, mapper e formatação de mensagens."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from midi_qwerty.config import (
    AppConfig,
    CCToggleAction,
    CCMomentaryAction,
    ConfigError,
    Mapping,
    NoteAction,
    PCAction,
    dumps,
    loads,
    normalize_key,
    save,
    validate,
)
from midi_qwerty.mapper import DOWN, UP, Mapper
from midi_qwerty.messages import (
    KIND_CC,
    KIND_NOTE_OFF,
    KIND_NOTE_ON,
    KIND_PC,
    MsgDesc,
    format_msg,
)


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

TOML_EXAMPLE = """
[midi]
port = "loopMIDI Port"

[capture]
toggle_key = "Scroll Lock"

[[map]]
key = "F1"
type = "cc_toggle"
channel = 0
cc = 20
on_value = 127
off_value = 0

[[map]]
key = "q"
type = "note"
channel = 1
note = 60
velocity = 100

[[map]]
key = "w"
type = "pc"
channel = 15
program = 3

[[map]]
key = "e"
type = "cc_momentary"
channel = 2
cc = 21
press_value = 100
release_value = 10
"""


def test_loads_roundtrip():
    cfg = loads(TOML_EXAMPLE)
    assert cfg.midi_port == "loopMIDI Port"
    assert cfg.toggle_key == "scroll lock"  # normalizado
    assert len(cfg.mappings) == 4

    m0 = cfg.mappings[0]
    assert m0.key == "f1"
    assert m0.action == CCToggleAction(0, 20, 127, 0)

    text = dumps(cfg)
    cfg2 = loads(text)
    assert cfg2 == cfg


def test_loads_rejects_unknown_type():
    with pytest.raises(ConfigError):
        loads('[[map]]\nkey="a"\ntype="foo"\n')


def test_loads_rejects_duplicate_keys():
    toml = '[[map]]\nkey="a"\ntype="pc"\nchannel=0\nprogram=1\n\n[[map]]\nkey="A"\ntype="pc"\nchannel=0\nprogram=2\n'
    with pytest.raises(ConfigError):
        loads(toml)


def test_loads_rejects_out_of_range():
    with pytest.raises(ConfigError):
        loads('[[map]]\nkey="a"\ntype="cc_toggle"\nchannel=16\ncc=1\n')
    with pytest.raises(ConfigError):
        loads('[[map]]\nkey="a"\ntype="note"\nvelocity=200\n')


def test_validate_ok():
    cfg = AppConfig(mappings=[Mapping("z", PCAction(0, 127))])
    validate(cfg)  # não deve lançar


def test_save_atomic_and_reload(tmp_path):
    path = str(tmp_path / "cfg.toml")
    cfg = loads(TOML_EXAMPLE)
    save(path, cfg)
    assert os.path.exists(path)
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
    assert load_file(path) == cfg


def load_file(path):
    from midi_qwerty.config import load as _load
    return _load(path)


def test_normalize_key():
    assert normalize_key(" Scroll   LOCK ") == "scroll lock"


# ---------------------------------------------------------------------------
# mapper
# ---------------------------------------------------------------------------

def test_cc_toggle_alternates():
    mp = Mapper()
    a = CCToggleAction(channel=0, cc=20, on_value=127, off_value=0)
    down1 = mp.handle("f1", DOWN, a)
    assert down1 == [MsgDesc(KIND_CC, 0, 20, 127)]
    assert mp.handle("f1", UP, a) == []  # soltar não envia nada em toggle
    down2 = mp.handle("f1", DOWN, a)
    assert down2 == [MsgDesc(KIND_CC, 0, 20, 0)]


def test_auto_repeat_ignored():
    mp = Mapper()
    a = NoteAction(0, 60, 100)
    first = mp.handle("q", DOWN, a)
    assert len(first) == 1 and first[0].kind == KIND_NOTE_ON
    assert mp.handle("q", DOWN, a) == []      # repeat
    second = mp.handle("q", UP, a)
    assert second[0].kind == KIND_NOTE_OFF
    assert mp.handle("q", UP, a) == []        # up sem down


def test_note_on_off():
    mp = Mapper()
    a = NoteAction(3, 72, 55)
    on = mp.handle("q", DOWN, a)
    off = mp.handle("q", UP, a)
    assert on[0].value == 55 and off[0].value == 0
    assert on[0].number == off[0].number == 72
    assert on[0].channel == 3


def test_pc_only_on_press():
    mp = Mapper()
    a = PCAction(5, 9)
    assert mp.handle("w", DOWN, a)[0] == MsgDesc(KIND_PC, 5, 9)
    assert mp.handle("w", UP, a) == []


def test_momentary_press_release():
    mp = Mapper()
    a = CCMomentaryAction(1, 7, 120, 0)
    press = mp.handle("e", DOWN, a)
    release = mp.handle("e", UP, a)
    assert press[0].value == 120 and release[0].value == 0


def test_release_all_sends_up_msgs():
    mp = Mapper()
    note_a = NoteAction(0, 60, 100)
    mom_a = CCMomentaryAction(0, 7, 127, 0)
    mp.handle("q", DOWN, note_a)
    mp.handle("e", DOWN, mom_a)
    msgs = mp.release_all()
    kinds = {m.kind for m in msgs}
    assert kinds == {KIND_NOTE_OFF, KIND_CC}
    assert mp.held_keys() == []
    # nova rodada de release não gera nada
    assert mp.release_all() == []


# ---------------------------------------------------------------------------
# messages
# ---------------------------------------------------------------------------

def test_format_msg():
    assert format_msg("f1", MsgDesc(KIND_CC, 0, 20, 127)) == "F1 → CC ch1 #20 = 127"
    assert format_msg("q", MsgDesc(KIND_PC, 15, 3)) == "Q → PC ch16 prog 3"
