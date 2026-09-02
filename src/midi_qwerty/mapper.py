"""Lógica de tradução tecla -> mensagens MIDI.

`Mapper` mantém o estado por tecla (pressionada? estado do toggle?) e
converte eventos down/up em `MsgDesc`. Cuida também do auto-repeat do
Windows: um segundo 'down' sem 'up' anterior é ignorado.
"""

from __future__ import annotations

from .config import Action
from .messages import MsgDesc

DOWN = "down"
UP = "up"


class _KeyState:
    __slots__ = ("held", "toggle_on", "action")

    def __init__(self) -> None:
        self.held = False
        self.toggle_on = False
        self.action: Action | None = None


class Mapper:
    def __init__(self) -> None:
        self._states: dict[str, _KeyState] = {}

    # ------------------------------------------------------------------
    def handle(self, key: str, event_type: str, action: Action) -> list[MsgDesc]:
        """Processa um evento de teclado e retorna mensagens a enviar.

        `key` já deve vir normalizado. Eventos de tecla não pressionada
        (auto-repeat) e 'up' sem 'down' são descartados.
        """
        st = self._states.setdefault(key, _KeyState())
        st.action = action

        if event_type == DOWN:
            if st.held:
                return []  # auto-repeat: ignora
            st.held = True
            return self._on_press(st, action)

        if event_type == UP:
            if not st.held:
                return []
            st.held = False
            return self._on_release(st, action)

        return []

    # ------------------------------------------------------------------
    def _on_press(self, st: _KeyState, a: Action) -> list[MsgDesc]:
        from .config import CCToggleAction, CCMomentaryAction, NoteAction, PCAction

        if isinstance(a, CCToggleAction):
            st.toggle_on = not st.toggle_on
            value = a.on_value if st.toggle_on else a.off_value
            return [MsgDesc("cc", a.channel, a.cc, value)]

        if isinstance(a, CCMomentaryAction):
            return [MsgDesc("cc", a.channel, a.cc, a.press_value)]

        if isinstance(a, NoteAction):
            return [MsgDesc("note_on", a.channel, a.note, a.velocity)]

        if isinstance(a, PCAction):
            return [MsgDesc("pc", a.channel, a.program)]

        return []

    def _on_release(self, st: _KeyState, a: Action) -> list[MsgDesc]:
        from .config import CCMomentaryAction, NoteAction

        if isinstance(a, CCMomentaryAction):
            return [MsgDesc("cc", a.channel, a.cc, a.release_value)]
        if isinstance(a, NoteAction):
            return [MsgDesc("note_off", a.channel, a.note, 0)]
        return []

    # ------------------------------------------------------------------
    def held_keys(self) -> list[str]:
        """Teclas atualmente pressionadas (para liberar ao desativar captura)."""
        return [k for k, s in self._states.items() if s.held]

    def release_all(self) -> list[MsgDesc]:
        """Gera mensagens de 'soltar' para toda tecla retida e limpa estado."""
        msgs: list[MsgDesc] = []
        for key in self.held_keys():
            st = self._states[key]
            if st.action is not None:
                msgs.extend(self._on_release(st, st.action))
            st.held = False
        return msgs

    def reset(self) -> None:
        """Limpa todo o estado (troca completa de mapeamento)."""
        self._states.clear()
