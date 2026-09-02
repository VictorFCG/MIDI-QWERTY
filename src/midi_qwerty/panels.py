"""Painel de edição de mapeamento (campos dinâmicos por tipo de ação)."""

from __future__ import annotations

import customtkinter as ctk

from .config import (
    Action,
    CCToggleAction,
    CCMomentaryAction,
    Mapping,
    NoteAction,
    PCAction,
)

ACCENT = "#1f6aa5"
ROW_BG = "#2b2b2b"
ROW_HOVER = "#383838"
ROW_SEL_BG = "#1f4e79"
BTN_SECONDARY = "#5d6d7e"
BTN_SECONDARY_HOVER = "#717d7e"
KEY_BADGE_BG = "#333333"
BADGE_BORDER = "#6b6b6b"
DANGER = "#7b241c"
DANGER_HOVER = "#943126"

TYPE_OPTIONS = [
    ("CC alternar (toggle)", "cc_toggle"),
    ("CC momentâneo", "cc_momentary"),
    ("Nota (note on/off)", "note"),
    ("Program Change", "pc"),
]

LABEL_TO_KIND = {l: k for l, k in TYPE_OPTIONS}
KIND_TO_LABEL = {k: l for l, k in TYPE_OPTIONS}

ACTION_TYPE_INFO = {
    "cc_toggle": {
        "fields": [
            ("cc_toggle_cc", "cc", 0, 127),
            ("cc_toggle_on_value", "on_value", 0, 127),
            ("cc_toggle_off_value", "off_value", 0, 127),
        ],
        "defaults": ["0", "127", "0"],
        "ctor": lambda ch, cc, ov, fv: CCToggleAction(ch, cc, ov, fv),
    },
    "cc_momentary": {
        "fields": [
            ("cc_momentary_cc", "cc", 0, 127),
            ("cc_momentary_press_value", "press_value", 0, 127),
            ("cc_momentary_release_value", "release_value", 0, 127),
        ],
        "defaults": ["0", "127", "0"],
        "ctor": lambda ch, cc, pv, rv: CCMomentaryAction(ch, cc, pv, rv),
    },
    "note": {
        "fields": [
            ("note", "note", 0, 127),
            ("velocity", "velocity", 0, 127),
        ],
        "defaults": ["60", "100"],
        "ctor": lambda ch, n, vel: NoteAction(ch, n, vel),
    },
    "pc": {
        "fields": [("program", "program", 0, 127)],
        "defaults": ["0"],
        "ctor": lambda ch, prog: PCAction(ch, prog),
    },
}

_LABEL_MAP = {
    "cc_toggle_cc": "CC:",
    "cc_toggle_on_value": "Valor ON:",
    "cc_toggle_off_value": "Valor OFF:",
    "cc_momentary_cc": "CC:",
    "cc_momentary_press_value": "Ao pressionar:",
    "cc_momentary_release_value": "Ao soltar:",
    "note": "Nota:",
    "velocity": "Velocidade:",
    "program": "Programa:",
}


class PanelController:
    def __init__(self, app) -> None:
        self._app = app
        self._font_bold: ctk.CTkFont | None = None
        self._font_normal: ctk.CTkFont | None = None
        self._font_small: ctk.CTkFont | None = None
        self._font_mono: ctk.CTkFont | None = None

    def set_fonts(self, bold: ctk.CTkFont, normal: ctk.CTkFont,
                  small: ctk.CTkFont, mono: ctk.CTkFont) -> None:
        self._font_bold = bold
        self._font_normal = normal
        self._font_small = small
        self._font_mono = mono

    def build_static_edit_widgets(self) -> None:
        app = self._app
        p = app._edit_panel
        for c in range(4):
            p.grid_columnconfigure(c, weight=0)
        p.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(p, text="", font=self._font_bold,
                     text_color="#7f8c8d").grid(
            row=0, column=0, columnspan=5, sticky="w", padx=12, pady=(8, 0))
        self._edit_title = p.grid_slaves(row=0, column=0)[0]

        ctk.CTkLabel(p, text="Tecla:", font=self._font_normal).grid(
            row=1, column=0, sticky="e", padx=(12, 6), pady=6)
        app._btn_map_key = ctk.CTkButton(
            p, text="Capturar tecla", width=110,
            fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
            command=app._start_capture_map_key)
        app._btn_map_key.grid(row=1, column=1, sticky="w", pady=6)
        app._lbl_map_key = ctk.CTkLabel(
            p, text="(nenhuma)", text_color="#e74c3c",
            font=self._font_bold, fg_color=KEY_BADGE_BG, corner_radius=6,
            border_width=1, border_color=BADGE_BORDER,
            width=90, height=28)
        app._lbl_map_key.grid(row=1, column=2, sticky="w", padx=(12, 6))

        ctk.CTkLabel(p, text="Tipo de ação:", font=self._font_normal).grid(
            row=2, column=0, sticky="e", padx=(12, 6), pady=6)
        app._menus = {}
        app._menus["type"] = ctk.CTkOptionMenu(
            p, values=list(LABEL_TO_KIND.keys()), width=200,
            command=lambda _v: self.on_type_changed())
        app._menus["type"].grid(row=2, column=1, sticky="w", pady=6)

        ctk.CTkLabel(p, text="Canal MIDI:", font=self._font_normal).grid(
            row=3, column=0, sticky="e", padx=(12, 6), pady=6)
        app._menus["channel"] = ctk.CTkOptionMenu(
            p, values=[str(c) for c in range(1, 17)], width=70,
            command=lambda _v: self.commit_from_panel())
        app._menus["channel"].grid(row=3, column=1, sticky="w", pady=6)

        self._entries: dict[str, ctk.CTkEntry] = {}
        self._build_type_frames()
        app._entries = self._entries

        app._warn_lbl = ctk.CTkLabel(
            p, text="", text_color="#e67e22", font=self._font_small,
            width=110,
        )
        app._warn_lbl.grid(row=99, column=0, columnspan=5,
                                 sticky="w", padx=12, pady=(2, 8))

    def _build_type_frames(self) -> None:
        app = self._app
        for _, kind in TYPE_OPTIONS:
            f = ctk.CTkFrame(app._edit_panel, fg_color="transparent")
            f.grid(row=4, column=0, columnspan=5, sticky="ew",
                         padx=12, pady=6)
            f.grid_remove()
            app._type_frames[kind] = f

        for kind, info in ACTION_TYPE_INFO.items():
            f = app._type_frames[kind]
            f.grid_columnconfigure(1, weight=0)
            f.grid_columnconfigure(3, weight=0)
            for i, (entry_name, _, _, _) in enumerate(info["fields"]):
                row = i
                col = 0 if i == 0 else 2
                label_text = _LABEL_MAP.get(entry_name, entry_name)
                ctk.CTkLabel(f, text=label_text,
                             font=self._font_normal).grid(
                    row=row, column=0, sticky="e", padx=(12, 6), pady=6)
                entry = ctk.CTkEntry(f, width=70, justify="center")
                entry.bind("<FocusOut>",
                           lambda _e, n=entry_name: self.commit_from_panel())
                entry.bind("<Return>",
                           lambda _e, n=entry_name: self.commit_from_panel())
                entry.grid(row=row, column=1, sticky="w", pady=6)
                self._entries[entry_name] = entry

    def rebuild_edit_panel(self) -> None:
        app = self._app
        for f in app._type_frames.values():
            f.grid_remove()

        if app._selected is None or not (0 <= app._selected < len(app._cfg.mappings)):
            self._edit_title.configure(
                text="Selecione uma tecla na lista ou adicione uma nova.")
            app._lbl_map_key.configure(text="(nenhuma)", text_color="#e74c3c")
            app._menus["type"].set("CC alternar (toggle)")
            app._menus["channel"].set("1")
            self.clear_entries()
            return

        m = app._cfg.mappings[app._selected]
        a = m.action
        self._edit_title.configure(text=f"Editando tecla {app._selected + 1}")
        app._lbl_map_key.configure(
            text=m.key.upper() if m.key else "(nenhuma)",
            text_color="#f1c40f" if m.key else "#e74c3c")
        app._menus["type"].set(KIND_TO_LABEL[a.kind])
        app._menus["channel"].set(str(a.channel + 1))
        self.fill_entries(a)
        app._type_frames[a.kind].grid()
        app._set_warn("")

    def fill_entries(self, action: Action) -> None:
        app = self._app
        self.clear_entries()
        info = ACTION_TYPE_INFO[action.kind]
        for entry_name, attr, _, _ in info["fields"]:
            app._entries[entry_name].delete(0, "end")
            app._entries[entry_name].insert(0, str(getattr(action, attr)))

    def clear_entries(self) -> None:
        app = self._app
        for entry in app._entries.values():
            entry.delete(0, "end")

    def fill_default_entries(self, kind: str) -> None:
        app = self._app
        self.clear_entries()
        info = ACTION_TYPE_INFO[kind]
        for (entry_name, _, _, _), default_val in zip(
                info["fields"], info["defaults"]):
            app._entries[entry_name].delete(0, "end")
            app._entries[entry_name].insert(0, default_val)

    def read_panel_into(self) -> bool:
        app = self._app
        if app._selected is None or not (
                0 <= app._selected < len(app._cfg.mappings)):
            return False
        old = app._cfg.mappings[app._selected]
        kind = LABEL_TO_KIND[app._menus["type"].get()]
        channel = int(app._menus["channel"].get()) - 1
        info = ACTION_TYPE_INFO[kind]
        vals: dict[str, int] = {}
        clamped: list[str] = []
        field_vals: list[int] = []
        for entry_name, attr, lo, hi in info["fields"]:
            ent = app._entries.get(entry_name)
            if ent is None:
                continue
            raw = ent.get().strip()
            try:
                orig = int(raw)
                v = max(lo, min(hi, orig))
            except ValueError:
                app._set_warn(
                    f"Valor inválido em '{entry_name}'. Use um inteiro.")
                return False
            if v != orig:
                clamped.append(f"{entry_name}: {orig} → {v}")
            vals[attr] = v
            field_vals.append(v)
        act = info["ctor"](channel, *field_vals)
        app._cfg.mappings[app._selected] = Mapping(key=old.key, action=act)
        if clamped:
            app._set_warn(
                "Ajustado ao limite MIDI (0–127): " + ", ".join(clamped))
        else:
            app._set_warn("")
        return True

    def on_type_changed(self) -> None:
        app = self._app
        kind = LABEL_TO_KIND[app._menus["type"].get()]
        for k, f in app._type_frames.items():
            f.grid() if k == kind else f.grid_remove()
        self.fill_default_entries(kind)
        if self.read_panel_into():
            app._commit(rebuild_list=True)

    def commit_from_panel(self) -> None:
        app = self._app
        if not self.read_panel_into():
            return
        if app._debounce_after is not None:
            try:
                app.after_cancel(app._debounce_after)
            except Exception:
                pass
        app._debounce_after = app.after(300, lambda: app._commit(rebuild_list=True))

    def set_warn(self, msg: str) -> None:
        app = self._app
        try:
            app._warn_lbl.configure(text=msg, width=110)
        except Exception:
            pass