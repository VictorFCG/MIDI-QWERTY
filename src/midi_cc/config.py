"""Configuração do midi_cc.

Define o modelo de dados do mapeamento (teclas -> ações MIDI) e a
serialização para/de TOML. O arquivo atual é salvo de forma atômica
(escrita em temporário + rename) para nunca corromper a config.

Estrutura do arquivo:

    [midi]
    port = "loopMIDI Port"

    [capture]
    toggle_key = "scroll lock"

    [[map]]
    key = "f1"
    type = "cc_toggle"
    channel = 0
    cc = 20
    on_value = 127
    off_value = 0

Canais são armazenados 0-based (0..15) e exibidos como 1..16 na GUI.
"""

from __future__ import annotations

import copy
import dataclasses
import os
import tomllib
from dataclasses import dataclass, field
from typing import Union


class ConfigError(ValueError):
    """Erro de validação/leitura do arquivo de configuração."""


# ---------------------------------------------------------------------------
# Ações
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CCToggleAction:
    """CC alternado: cada pressionada alterna entre off_value e on_value."""
    kind = "cc_toggle"
    channel: int = 0
    cc: int = 0
    on_value: int = 127
    off_value: int = 0


@dataclass(frozen=True)
class CCMomentaryAction:
    """CC momentâneo: tecla pressionada = press_value, solta = release_value."""
    kind = "cc_momentary"
    channel: int = 0
    cc: int = 0
    press_value: int = 127
    release_value: int = 0


@dataclass(frozen=True)
class NoteAction:
    """Nota musical: Note On ao apertar, Note Off ao soltar."""
    kind = "note"
    channel: int = 0
    note: int = 60
    velocity: int = 100


@dataclass(frozen=True)
class PCAction:
    """Program Change enviado ao pressionar a tecla."""
    kind = "pc"
    channel: int = 0
    program: int = 0


Action = Union[CCToggleAction, CCMomentaryAction, NoteAction, PCAction]

_ACTION_CLASSES = {
    c.kind: c for c in (CCToggleAction, CCMomentaryAction, NoteAction, PCAction)
}


@dataclass(frozen=True)
class Mapping:
    """Uma tecla mapeada a uma ação. key == "" significa 'indefinida'."""
    key: str
    action: Action


@dataclasses.dataclass
class AppConfig:
    """Estado completo e mutável da aplicação (arquivo vivo)."""
    midi_port: str = "loopMIDI Port"
    toggle_key: str = "scroll lock"
    mappings: list[Mapping] = field(default_factory=list)

    def copy(self) -> "AppConfig":
        return copy.deepcopy(self)

    def find_by_key(self, key: str) -> Mapping | None:
        key = normalize_key(key)
        for m in self.mappings:
            if m.key == key:
                return m
        return None

    def has_key(self, key: str, *, exclude_index: int | None = None) -> bool:
        key = normalize_key(key)
        if not key:
            return False
        for i, m in enumerate(self.mappings):
            if i != exclude_index and m.key == key:
                return True
        return False


def normalize_key(key: str) -> str:
    """Normaliza nome de tecla: minúsculas, espaços simples."""
    return " ".join(key.lower().split())


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------

def _clamp(name: str, value: int, lo: int, hi: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"'{name}' deve ser inteiro (recebido: {value!r})")
    if not (lo <= value <= hi):
        raise ConfigError(f"'{name}' fora do intervalo {lo}..{hi} (recebido: {value})")
    return value


def _parse_action(d: dict, index: int) -> Action:
    kind = d.get("type")
    cls = _ACTION_CLASSES.get(kind)
    if cls is None:
        raise ConfigError(
            f"map[{index}]: tipo desconhecido {kind!r}. "
            f"Válidos: {', '.join(sorted(_ACTION_CLASSES))}"
        )
    fields = {f.name: f for f in dataclasses.fields(cls)}
    kwargs = {}
    for name, f in fields.items():
        if name == "kind":
            continue
        raw = d.get(name, getattr(cls(), name))
        hi = 15 if name == "channel" else 127
        kwargs[name] = _clamp(name, raw, 0, hi)
    return cls(**kwargs)


def validate(cfg: AppConfig) -> None:
    """Valida limites MIDI. Levanta ConfigError em caso de problema."""
    for i, m in enumerate(cfg.mappings):
        _parse_action({"type": m.action.kind, **dataclasses.asdict(m.action)}, i)


# ---------------------------------------------------------------------------
# Serialização TOML
# ---------------------------------------------------------------------------

def _toml_str(s: str) -> str:
    import json
    return json.dumps(s, ensure_ascii=False)


def dumps(cfg: AppConfig) -> str:
    lines: list[str] = ["# Arquivo gerado pelo midi_cc — pode ser editado à mão.", ""]
    lines += ["[midi]", f"port = {_toml_str(cfg.midi_port)}", ""]
    lines += ["[capture]", f"toggle_key = {_toml_str(cfg.toggle_key)}", ""]
    for m in cfg.mappings:
        lines.append("[[map]]")
        lines.append(f"key = {_toml_str(m.key)}")
        a = m.action
        lines.append(f"type = {_toml_str(a.kind)}")
        lines.append(f"channel = {a.channel}")
        if isinstance(a, CCToggleAction):
            lines += [f"cc = {a.cc}", f"on_value = {a.on_value}", f"off_value = {a.off_value}"]
        elif isinstance(a, CCMomentaryAction):
            lines += [f"cc = {a.cc}", f"press_value = {a.press_value}", f"release_value = {a.release_value}"]
        elif isinstance(a, NoteAction):
            lines += [f"note = {a.note}", f"velocity = {a.velocity}"]
        elif isinstance(a, PCAction):
            lines.append(f"program = {a.program}")
        lines.append("")
    return "\n".join(lines)


def loads(text: str) -> AppConfig:
    """Faz parse de TOML para AppConfig. Levanta ConfigError se inválido."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"TOML inválido: {e}") from e

    cfg = AppConfig()
    midi = data.get("midi") or {}
    capture = data.get("capture") or {}
    cfg.midi_port = str(midi.get("port", cfg.midi_port))
    cfg.toggle_key = normalize_key(str(capture.get("toggle_key", cfg.toggle_key)))

    maps = data.get("map", [])
    if not isinstance(maps, list):
        raise ConfigError("'map' deve ser uma lista de tabelas [[map]]")
    seen: set[str] = set()
    for i, d in enumerate(maps):
        if not isinstance(d, dict):
            raise ConfigError(f"map[{i}]: entrada inválida")
        key = normalize_key(str(d.get("key", "")))
        if key:
            if key in seen:
                raise ConfigError(f"map[{i}]: tecla duplicada '{key}'")
            seen.add(key)
        cfg.mappings.append(Mapping(key=key, action=_parse_action(d, i)))
    validate(cfg)
    return cfg


# ---------------------------------------------------------------------------
# Arquivo
# ---------------------------------------------------------------------------

def load(path: str) -> AppConfig:
    with open(path, "rb") as f:
        return loads(f.read().decode("utf-8"))


def save(path: str, cfg: AppConfig) -> None:
    """Salva atomicamente: escreve em .tmp no mesmo diretório e renomeia."""
    text = dumps(cfg)
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = os.path.join(directory, f".{os.path.basename(path)}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def default() -> AppConfig:
    """Config inicial com dois exemplos (editáveis pela GUI)."""
    return AppConfig(
        midi_port="loopMIDI Port",
        toggle_key="scroll lock",
        mappings=[
            Mapping(key="f1", action=CCToggleAction(channel=0, cc=20)),
            Mapping(key="f2", action=PCAction(channel=0, program=3)),
        ],
    )
