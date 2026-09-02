"""Saída MIDI via mido/rtmidi.

A aplicação envia para uma porta MIDI-out existente no sistema — na
prática, uma porta virtual criada pelo loopMIDI, que a DAW enxerga
como um dispositivo de entrada comum.
"""

from __future__ import annotations

import threading

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
    """Wrapper thread-safe sobre mido.

    open/close chegam pela thread worker da engine e send também pode vir
    dos callbacks de teclado — cada operação é atômica entre si.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._out: mido.ports.BaseOutput | None = None
        self._name: str | None = None

    # ------------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._out is not None

    @property
    def name(self) -> str | None:
        with self._lock:
            return self._name

    def open(self, name: str) -> None:
        """Abre a porta; fecha a anterior se houver. Levanta exceção se falhar."""
        with self._lock:
            self.close()
            self._out = mido.open_output(name)
            self._name = name

    def close(self) -> None:
        with self._lock:
            if self._out is not None:
                try:
                    self._out.close()
                except Exception:
                    pass
                self._out = None
                self._name = None

    def send(self, msg: MsgDesc) -> None:
        """Envia uma MsgDesc; erro é propagado (engine decide o que fazer)."""
        with self._lock:
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
