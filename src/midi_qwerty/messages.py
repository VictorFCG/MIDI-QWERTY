"""Descrições de mensagens MIDI (independentes de biblioteca).

O mapper produz `MsgDesc` (estruturas simples e testáveis); o módulo
`midi` converte para objetos `mido.Message`. Isso mantém a lógica de
mapeamento 100% testável sem hardware/porta MIDI.
"""

from __future__ import annotations

from dataclasses import dataclass

KIND_CC = "cc"
KIND_NOTE_ON = "note_on"
KIND_NOTE_OFF = "note_off"
KIND_PC = "pc"


@dataclass(frozen=True)
class MsgDesc:
    """Mensagem MIDI abstrata.

    - cc:       number=controlador, value=valor
    - note_on/off: number=nota, value=velocity
    - pc:       number=programa, value ignorado
    """
    kind: str
    channel: int
    number: int
    value: int = 0


def describe_action(action) -> str:
    """Resumo curto da ação para exibição na lista da GUI."""
    ch = action.channel + 1
    if action.kind == "cc_toggle":
        return f"CC#{action.cc} toggle ch{ch}"
    if action.kind == "cc_momentary":
        return f"CC#{action.cc} momentâneo ch{ch}"
    if action.kind == "note":
        return f"Nota {action.note} ch{ch}"
    if action.kind == "pc":
        return f"PC {action.program} ch{ch}"
    return "?"


def format_msg(key: str, msg: MsgDesc) -> str:
    """Formata uma mensagem enviada para o monitor da GUI."""
    key_part = key.upper() if key else "?"
    ch = msg.channel + 1
    if msg.kind == KIND_CC:
        return f"{key_part} → CC ch{ch} #{msg.number} = {msg.value}"
    if msg.kind == KIND_NOTE_ON:
        return f"{key_part} → Note On {msg.number} vel{msg.value} ch{ch}"
    if msg.kind == KIND_NOTE_OFF:
        return f"{key_part} → Note Off {msg.number} ch{ch}"
    if msg.kind == KIND_PC:
        return f"{key_part} → PC ch{ch} prog {msg.number}"
    return f"{key_part} → {msg.kind}"
