"""Engine de captura e envio MIDI (roda fora da thread da GUI).

Responsabilidades:
- registrar/desregistrar hooks globais por tecla quando o modo captura
  liga/desliga (teclas mapeadas são *engolidas* — não digitam nada);
- alternar o modo captura pela tecla gatilho ou por comando da GUI;
- converter eventos de teclado em mensagens MIDI via `Mapper` e enviá-las;
- publicar eventos (mensagens enviadas, status) numa fila que a GUI consome.

Concorrência: a GUI chama `apply_config`/`set_capture`/`toggle`; os callbacks
de teclado chegam na thread do `keyboard`. Toda mutação de estado passa pela
fila de comandos processada por um único worker, serializando o acesso aos
hooks e à porta MIDI (evita mexer nos hooks dentro da própria thread de hook).
"""

from __future__ import annotations

import copy
import queue
import threading
import time
from collections import deque

import keyboard

from .config import AppConfig, Mapping, normalize_key
from .mapper import Mapper
from .messages import format_msg
from .midi import MidiPort, list_output_ports


class Engine:
    def __init__(self, cfg: AppConfig) -> None:
        self._lock = threading.RLock()
        self._cfg: AppConfig = cfg.copy()
        self._port = MidiPort()
        self._mapper = Mapper()

        self._capture_active = False
        self._hooked: set[str] = set()
        self._toggle_hk = None  # handle do add_hotkey da tecla gatilho

        self._cmds: queue.Queue[tuple] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False

        # Eventos para a GUI consumir (strings já formatadas com timestamp)
        self.events: deque[str] = deque(maxlen=200)

    # ==================================================================
    # API pública (thread-safe; enfileira comandos)
    # ==================================================================

    def start(self) -> None:
        self._running = True
        self._worker = threading.Thread(target=self._work, name="midi-qwerty-engine", daemon=True)
        self._worker.start()
        self.apply_config(self._cfg)

    def stop(self) -> None:
        self._running = False
        self._cmds.put(("shutdown", None))
        if self._worker is not None:
            self._worker.join(timeout=3)

    def apply_config(self, cfg: AppConfig) -> None:
        """Substitui a config viva (portas, gatilho, mapeamentos)."""
        self._cmds.put(("apply", cfg.copy()))

    def toggle_capture(self) -> None:
        self._cmds.put(("toggle", None))

    def set_capture(self, active: bool) -> None:
        self._cmds.put(("capture", active))

    def list_ports(self) -> list[str]:
        """Portas MIDI-out disponíveis agora."""
        return list_output_ports()

    # ------------------------------------------------------------------
    # Snapshots de leitura para a GUI
    # ------------------------------------------------------------------

    def capture_active(self) -> bool:
        with self._lock:
            return self._capture_active

    def port_name(self) -> str | None:
        with self._lock:
            return self._port.name

    def config(self) -> AppConfig:
        """Cópia da config atualmente aplicada."""
        with self._lock:
            return self._cfg.copy()

    def push_event(self, text: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.events.appendleft(f"[{ts}] {text}")

    # ==================================================================
    # Worker: processa comandos em série
    # ==================================================================

    def _work(self) -> None:
        try:
            while True:
                try:
                    cmd, arg = self._cmds.get(timeout=0.2)
                except queue.Empty:
                    if not self._running:
                        break
                    continue
                if cmd == "shutdown":
                    break
                try:
                    if cmd == "apply":
                        self._apply(arg)
                    elif cmd == "toggle":
                        self._set_capture(not self.capture_active())
                    elif cmd == "capture":
                        self._set_capture(bool(arg))
                except Exception as e:  # nunca deixar o worker morrer
                    self.push_event(f"ERRO interno: {e!r}")
        finally:
            self._shutdown_cleanup()

    def _shutdown_cleanup(self) -> None:
        with self._lock:
            self._unhook_all_locked()
            self._send_locked(self._mapper.release_all())
            self._capture_active = False
            self._port.close()

    # ==================================================================
    # Aplicação de configuração
    # ==================================================================

    def _apply(self, new_cfg: AppConfig) -> None:
        with self._lock:
            old_cfg = self._cfg

            # Solta o que estiver retido e limpa estado antes de trocar tudo
            self._unhook_all_locked()
            self._send_locked(self._mapper.release_all())

            self._cfg = new_cfg

            # Tecla gatilho do modo captura (registra na 1ª vez e em mudanças)
            if (self._toggle_hk is None
                    or normalize_key(old_cfg.toggle_key) != normalize_key(new_cfg.toggle_key)):
                self._register_toggle_key(new_cfg.toggle_key)

            # Porta MIDI
            want = new_cfg.midi_port
            if not self._port.is_open or self._port.name != want:
                self._open_port(want)

            # Re-hook se o modo captura estiver ligado
            if self._capture_active:
                self._hook_mapped_locked()

            self.push_event("Configuração aplicada.")

    def _register_toggle_key(self, key: str) -> None:
        """(Re)registra a hotkey global que alterna o modo captura."""
        if self._toggle_hk is not None:
            try:
                keyboard.remove_hotkey(self._toggle_hk)
            except (KeyError, ValueError):
                pass
            self._toggle_hk = None
        key = normalize_key(key)
        if key:
            self._toggle_hk = keyboard.add_hotkey(
                key, lambda: self.toggle_capture(), suppress=False, trigger_on_release=False
            )

    def _open_port(self, name: str) -> None:
        try:
            self._port.open(name)
            self.push_event(f"Porta MIDI aberta: {name}")
        except Exception as e:
            self._port.close()
            self.push_event(f"ERRO ao abrir porta '{name}': {e}")

    # ==================================================================
    # Modo captura / hooks
    # ==================================================================

    def _set_capture(self, active: bool) -> None:
        with self._lock:
            if active == self._capture_active:
                return
            if active:
                self._hook_mapped_locked()
                self._capture_active = True
                self.push_event("▶ Modo captura ATIVADO")
            else:
                self._capture_active = False
                self._unhook_all_locked()
                self._send_locked(self._mapper.release_all())
                self.push_event("■ Modo captura DESATIVADO")

    def _mapped_keys(self) -> list[Mapping]:
        seen: set[str] = set()
        out: list[Mapping] = []
        for m in self._cfg.mappings:
            k = normalize_key(m.key)
            if k and k not in seen:
                seen.add(k)
                out.append(m)
        return out

    def _hook_mapped_locked(self) -> None:
        self._unhook_all_locked()
        for m in self._mapped_keys():
            k = normalize_key(m.key)
            try:
                keyboard.hook_key(k, self._make_cb(k), suppress=True)
                self._hooked.add(k)
            except Exception as e:
                self.push_event(f"ERRO ao capturar tecla '{k}': {e}")

    def _unhook_all_locked(self) -> None:
        for k in list(self._hooked):
            try:
                keyboard.unhook_key(k)
            except (KeyError, ValueError):
                pass
        self._hooked.clear()

    def _make_cb(self, key: str):
        def cb(event) -> None:
            etype = "down" if event.event_type == "down" else "up"
            self._on_key(key, etype)

        return cb

    # ==================================================================
    # Evento de tecla -> MIDI
    # ==================================================================

    def _on_key(self, key: str, event_type: str) -> None:
        with self._lock:
            if not self._capture_active:
                return
            mapping = self._cfg.find_by_key(key)
            if mapping is None:
                return
            for d in self._mapper.handle(key, event_type, mapping.action):
                line = format_msg(key, d)
                try:
                    self._port.send(d)
                except Exception as e:
                    line += f"   ⚠ sem porta ({e})"
                self.push_event(line)

    def _send_locked(self, msgs) -> None:
        for d in msgs:
            try:
                self._port.send(d)
            except Exception:
                pass
