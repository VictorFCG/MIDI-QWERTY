"""Saída MIDI via mido/rtmidi.

A aplicação envia para uma porta MIDI-out existente no sistema — na
prática, uma porta virtual criada pelo loopMIDI, que a DAW enxerga
como um dispositivo de entrada comum.
"""

from __future__ import annotations

import mido

from .messages import (
    KIND_CC,
    KIND_NOTE_OFF,
    KIND_NOTE_ON,
    KIND_PC,
    MsgDesc,
)

try:
    mido.set_backend("mido.backends.rtmidi")
except Exception:  # pragma: no cover - backend padrão já pode estar ok
    pass


def list_output_ports() -> list[str]:
    """Nomes das portas MIDI-out disponíveis. [] em caso de erro."""
    try:
        return sorted(mido.get_output_names())
    except Exception:
        return []


class MidiPort:
    """Wrapper fino e thread-safe o suficiente sobre mido.ports.BaseOutput."""

    def __init__(self) -> None:
        self._out: mido.ports.BaseOutput | None = None
        self.name: str | None = None

    # ------------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self._out is not None

    def open(self, name: str) -> None:
        """Abre a porta; fecha a anterior se houver. Levanta exceção se falhar."""
        self.close()
        self._out = mido.open_output(name)
        self.name = name

    def close(self) -> None:
        if self._out is not None:
            try:
                self._out.close()
            except Exception:
                pass
            self._out = None
            self.name = None

    def send(self, msg: MsgDesc) -> None:
        """Envia uma MsgDesc; erro é propagado (engine decide o que fazer)."""
        out = self._out
        if out is None:
            raise RuntimeError("porta MIDI não aberta")
        out.send(to_mido(msg))


def to_mido(msg: MsgDesc) -> mido.Message:
    """Converte MsgDesc -> mido.Message."""
    if msg.kind == KIND_CC:
        return mido.Message("control_change", channel=msg.channel,
                            control=msg.number, value=msg.value)
    if msg.kind == KIND_NOTE_ON:
        return mido.Message("note_on", channel=msg.channel,
                            note=msg.number, velocity=msg.value)
    if msg.kind == KIND_NOTE_OFF:
        return mido.Message("note_off", channel=msg.channel,
                            note=msg.number, velocity=0)
    if msg.kind == KIND_PC:
        return mido.Message("program_change", channel=msg.channel,
                            program=msg.number)
    raise ValueError(f"tipo de mensagem desconhecido: {msg.kind!r}")
