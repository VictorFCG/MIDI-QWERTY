"""Interface gráfica (CustomTkinter).

Janela única com:
- seleção da porta MIDI-out (loopMIDI);
- lista de teclas mapeadas (adicionar/remover/selecionar);
- painel integrado de edição da tecla selecionada (captura física de tecla,
  tipo de ação e campos dinâmicos por tipo);
- tecla gatilho do modo captura;
- botão liga/desliga do modo captura + monitor em tempo real das mensagens.

Toda alteração é auto-salva no arquivo principal e aplicada na engine na hora.
Exportar grava um snapshot à parte; importar copia o conteúdo para o arquivo
atual sem jamais modificar o arquivo importado.
"""

from __future__ import annotations

import os
import tkinter.filedialog as fd
import tkinter.messagebox as mb

import customtkinter as ctk

from . import config as cfgmod
from .config import (
    AppConfig,
    Action,
    CCToggleAction,
    CCMomentaryAction,
    Mapping,
    NoteAction,
    PCAction,
    normalize_key,
)
from .engine import Engine
from .messages import describe_action

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

# Fontes padronizadas
FONT_FAMILY = "Segoe UI" if os.name == "nt" else "DejaVu Sans"
FONT_SIZE = 12
FONT_BOLD = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE, weight="bold")
FONT_NORMAL = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE)
FONT_SMALL = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE - 1)
FONT_MONO = ctk.CTkFont(family="Consolas", size=13)

TYPE_OPTIONS = [  # (rótulo exibido, kind)
    ("CC alternar (toggle)", "cc_toggle"),
    ("CC momentâneo", "cc_momentary"),
    ("Nota (note on/off)", "note"),
    ("Program Change", "pc"),
]

BASE_TITLE = "MIDI-QWERTY — teclado QWERTY → MIDI"

_TK_KEYMAP = {
    "escape": "esc",
    "return": "enter",
    "kp_enter": "enter",
    "space": "space",
    "caps_lock": "caps lock",
    "scroll_lock": "scroll lock",
    "num_lock": "num lock",
    "print": "print screen",
    "prior": "page up",
    "next": "page down",
    "left": "left arrow",
    "right": "right arrow",
    "up": "up arrow",
    "down": "down arrow",
    "control_l": "left ctrl",
    "control_r": "right ctrl",
    "alt_l": "left alt",
    "alt_r": "right alt",
    "shift_l": "left shift",
    "shift_r": "right shift",
    "win_l": "left windows",
    "win_r": "right windows",
    "backspace": "backspace",
}


def tk_keysym_to_name(keysym: str) -> str:
    """Converte keysym do Tk para o nome usado pela lib `keyboard`."""
    ks = keysym.lower()
    return _TK_KEYMAP.get(ks, ks.replace("_", " "))


class CTkToolTip:
    """Tooltip simples para CustomTkinter."""

    def __init__(self, widget: ctk.CTkBaseClass, text: str, delay: int = 500) -> None:
        self._widget = widget
        self._text = text
        self._delay = delay
        self._tip: ctk.CTkToplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)
        widget.bind("<ButtonPress>", self._on_leave)

    def _on_enter(self, _event=None) -> None:
        self._after_id = self._widget.after(self._delay, self._show_tip)

    def _on_leave(self, _event=None) -> None:
        if self._after_id is not None:
            self._widget.after_cancel(self._after_id)
            self._after_id = None
        self._hide_tip()

    def _show_tip(self) -> None:
        if self._tip is not None:
            return
        x = self._widget.winfo_pointerx() + 10
        y = self._widget.winfo_pointery() + 10
        self._tip = ctk.CTkToplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        self._tip.attributes("-topmost", True)
        label = ctk.CTkLabel(self._tip, text=self._text, fg_color="#2b2b2b",
                             corner_radius=6, padx=8, pady=4,
                             text_color="#ecf0f1", font=FONT_SMALL)
        label.pack()
        self._tip.lift()

    def _hide_tip(self) -> None:
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class MidiQwertyApp(ctk.CTk):
    def __init__(self, engine: Engine, cfg: AppConfig, cfg_path: str) -> None:
        super().__init__()
        self._engine = engine
        self._cfg = cfg
        self._cfg_path = cfg_path

        self._selected: int | None = None      # índice selecionado na lista
        self._capturing: tuple | None = None   # ("mapping", idx) | ("toggle", None)
        self._monitor_count = 0
        self._pending_delete: int | None = None
        self._pending_delete_after = None
        self._delete_buttons: dict[int, ctk.CTkButton] = {}
        self._row_pool: list[ctk.CTkFrame] = []  # pool de linhas reutilizáveis
        self._row_widgets: dict[int, tuple[ctk.CTkFrame, ctk.CTkButton, ctk.CTkButton]] = {}  # idx -> (row, btn, del_btn)
        self._debounce_after: str | None = None  # timer para debounce do auto-save

        self.title(BASE_TITLE)
        geo = self._initial_geometry()
        self.geometry(geo)
        gw, gh = (int(x) for x in geo.split("+")[0].split("x"))
        self.minsize(min(960, gw), min(700, gh))

        # Tema e fontes
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")  # tema padrão do CustomTkinter
        self._apply_fonts()

        self._build_ui()
        self._refresh_ports(select=cfg.midi_port)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Loop de atualização (monitor/status) — drena a fila da engine
        self.after(150, self._poll)

    # ==================================================================
    # Construção da UI
    # ==================================================================

    def _build_ui(self) -> None:
        # Layout fixo: barra da porta no topo; corpo em DUAS colunas iguais
        # (uniform="cols"): lista/edição à esquerda e monitor/controle da
        # interceptação à direita. Só a linha da lista é flexível — nada
        # "salta" ao popular a lista.
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Linha 0: porta MIDI (largura total) ----------------------
        top = ctk.CTkFrame(self)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 6))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="Saída MIDI:", font=FONT_NORMAL).grid(row=0, column=0, padx=(10, 6), pady=10)
        self._port_menu = ctk.CTkOptionMenu(
            top, values=["(sem portas)"], width=320,
            command=self._on_port_selected,
        )
        self._port_menu.set("(sem portas)")
        self._port_menu.grid(row=0, column=1, sticky="w", pady=10)
        CTkToolTip(self._port_menu, "Selecionar porta de saída MIDI (loopMIDI)")
        btn_refresh = ctk.CTkButton(top, text="↻ Atualizar", width=90,
                      command=self._refresh_ports_clicked)
        btn_refresh.grid(row=0, column=2, padx=6, pady=10)
        CTkToolTip(btn_refresh, "Reescanear portas MIDI disponíveis\n(útil se criou a porta depois de abrir o app)")
        self._port_status = ctk.CTkLabel(top, text="● desconectado", text_color="#c0392b")
        self._port_status.grid(row=0, column=3, padx=(6, 12), pady=10)

        # --- Corpo em 2 colunas (uniform: lista==edição, monitor==controle) ---
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=12, pady=6)
        body.grid_columnconfigure(0, weight=1, uniform="cols")
        body.grid_columnconfigure(1, weight=1, uniform="cols")
        # A LINHA FLEXÍVEL é a 1 (lista/edição/controle); a 0 tem só cabeçalhos
        body.grid_rowconfigure(1, weight=1)
        self._body = body

        # Coluna ESQUERDA (3): cabeçalho / LISTA (flexível) / edição
        head = ctk.CTkFrame(body, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 2))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="Teclas mapeadas (clique para editar):", font=FONT_BOLD).grid(row=0, column=0, sticky="w")
        btn_import = ctk.CTkButton(head, text="Importar", width=90, fg_color=BTN_SECONDARY,
                      hover_color=BTN_SECONDARY_HOVER, command=self._import)
        btn_import.grid(row=0, column=1, padx=(0, 6))
        CTkToolTip(btn_import, "Importar mapeamento de um arquivo TOML\n(substitui o mapeamento atual)")

        btn_export = ctk.CTkButton(head, text="Exportar", width=90, fg_color=BTN_SECONDARY,
                      hover_color=BTN_SECONDARY_HOVER, command=self._export)
        btn_export.grid(row=0, column=2, padx=(0, 6))
        CTkToolTip(btn_export, "Exportar mapeamento atual para um arquivo TOML\n(cria um snapshot/preset)")

        btn_add = ctk.CTkButton(head, text="+ Adicionar tecla", width=140,
                      command=self._add_mapping)
        btn_add.grid(row=0, column=3)
        CTkToolTip(btn_add, "Adicionar novo mapeamento de tecla\n(e entrar em modo de captura)")

        self._list_frame = ctk.CTkScrollableFrame(body)
        self._list_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=2)
        self._list_frame.grid_columnconfigure(0, weight=1)

        self._edit_panel = ctk.CTkFrame(body)
        self._edit_panel.grid(row=2, column=0, sticky="ew", padx=(0, 6), pady=(8, 0))
        self._edit_panel.grid_columnconfigure(1, weight=1)

        # --- Frames por tipo de ação (show/hide em vez de rebuild) ---
        self._type_frames: dict[str, ctk.CTkFrame] = {}
        for _, kind in TYPE_OPTIONS:
            f = ctk.CTkFrame(self._edit_panel, fg_color="transparent")
            f.grid(row=4, column=0, columnspan=5, sticky="ew", padx=12, pady=6)
            f.grid_remove()
            self._type_frames[kind] = f

        # --- Widgets estáticos do painel (criados uma vez) ---
        self._build_static_edit_widgets()

        # Trilha DIREITA (2): monitor no alto + controle da interceptação
        # embaixo — um único frame com rowspan sobre as 3 linhas da esquerda
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=(6, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)  # monitor absorve a sobra vertical
        mhead = ctk.CTkFrame(right, fg_color="transparent")
        mhead.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        mhead.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(mhead, text="Monitor de mensagens enviadas:",
                     anchor="w").grid(row=0, column=0, sticky="w")
        btn_clear = ctk.CTkButton(mhead, text="Limpar", width=70, height=24,
                      fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                      command=self._clear_monitor)
        btn_clear.grid(row=0, column=1, padx=(6, 0))
        CTkToolTip(btn_clear, "Limpar o monitor de mensagens MIDI")
        self._monitor = ctk.CTkTextbox(right, state="disabled", wrap="none",
                                       font=FONT_MONO)
        self._monitor.grid(row=1, column=0, sticky="nsew")
        self._monitor.tag_config("err", foreground="#e74c3c")

        ctk.CTkLabel(right, text="Controle da interceptação:",
                     font=FONT_BOLD,
                     text_color="#7f8c8d").grid(row=2, column=0, sticky="w", pady=(14, 0))
        self._btn_capture = ctk.CTkButton(right, text="▶ Ativar interceptação agora",
                                          width=220, command=self._toggle_capture_clicked)
        self._btn_capture.grid(row=3, column=0, sticky="ew", pady=4)
        CTkToolTip(self._btn_capture, "Ativar/desativar a interceptação de teclas\n(também: tecla Scroll Lock)")
        self._lbl_mode = ctk.CTkLabel(right, text="Interceptação: INATIVA",
                                      text_color="#95a5a6", font=FONT_BOLD)
        self._lbl_mode.grid(row=4, column=0, sticky="w")

        ctk.CTkLabel(right, text="Tecla que liga/desliga:").grid(
            row=5, column=0, sticky="w", pady=(12, 0))
        trigrow = ctk.CTkFrame(right, fg_color="transparent")
        trigrow.grid(row=6, column=0, sticky="ew", pady=2)
        self._btn_trig_cap = ctk.CTkButton(trigrow, text="Capturar tecla", width=110,
                                           fg_color=BTN_SECONDARY,
                                           hover_color=BTN_SECONDARY_HOVER,
                                           command=self._start_capture_toggle_key)
        self._btn_trig_cap.pack(side="left")
        CTkToolTip(self._btn_trig_cap, "Definir qual tecla alterna a interceptação\n(padrão: Scroll Lock)")
        self._lbl_trig_val = ctk.CTkLabel(trigrow, text=(self._cfg.toggle_key or "(desativado)").upper(),
                                          text_color="#f1c40f" if self._cfg.toggle_key else "#e74c3c",
                                          font=FONT_BOLD,
                                          fg_color=KEY_BADGE_BG, corner_radius=6,
                                          border_width=1, border_color=BADGE_BORDER,
                                          width=110, height=28)
        self._lbl_trig_val.pack(side="left", padx=(8, 0))
        self._lbl_trig_hint = ctk.CTkLabel(right, text="", text_color="#e67e22",
                                           wraplength=300, justify="left")
        self._lbl_trig_hint.grid(row=7, column=0, sticky="w", pady=(0, 2))

        self._rebuild_list()
        self._rebuild_edit_panel()

        # Navegação por teclado na lista (↑/↓ seleciona, Del remove)
        self.bind("<Up>", lambda _e: (self._move_selection(-1), "break")[1])
        self.bind("<Down>", lambda _e: (self._move_selection(1), "break")[1])
        self.bind("<Delete>", self._on_delete_key)

    def _initial_geometry(self) -> str:
        """Janela padrão, clamped à tela (notebooks com 768px de altura)."""
        # Tenta usar geometria salva no config
        cfg = self._cfg
        if cfg.window_x is not None and cfg.window_y is not None and cfg.window_w is not None and cfg.window_h is not None:
            return f"{cfg.window_w}x{cfg.window_h}+{cfg.window_x}+{cfg.window_y}"

        try:
            sw = int(self.winfo_screenwidth())
            sh = int(self.winfo_screenheight())
        except Exception:
            return "1120x800"
        w = max(min(1120, sw - 60), 900)
        h = max(min(800, sh - 100), 600)
        return f"{w}x{h}"

    def _apply_fonts(self) -> None:
        """Aplica fontes padronizadas aos widgets CustomTkinter globais."""
        # CustomTkinter não tem API global de fonte, mas podemos configurar
        # o tema padrão que afeta novos widgets
        pass  # Fontes são aplicadas via FONT_* constants nos widgets

    def _build_static_edit_widgets(self) -> None:
        """Cria widgets estáticos do painel de edição (tecla, tipo, canal) uma única vez."""
        p = self._edit_panel

        # Grid em 4 colunas pareadas + espaçador
        for c in range(4):
            p.grid_columnconfigure(c, weight=0)
        p.grid_columnconfigure(4, weight=1)

        # Título (linha 0)
        self._edit_title = ctk.CTkLabel(p, text="", font=FONT_BOLD,
                                        text_color="#7f8c8d")
        self._edit_title.grid(row=0, column=0, columnspan=5, sticky="w", padx=12, pady=(8, 0))

        # Tecla (linha 1)
        ctk.CTkLabel(p, text="Tecla:", font=FONT_NORMAL).grid(row=1, column=0, sticky="e", padx=(12, 6), pady=6)
        self._btn_map_key = ctk.CTkButton(p, text="Capturar tecla", width=110,
                                          fg_color=BTN_SECONDARY,
                                          hover_color=BTN_SECONDARY_HOVER,
                                          command=self._start_capture_map_key)
        self._btn_map_key.grid(row=1, column=1, sticky="w", pady=6)
        CTkToolTip(self._btn_map_key, "Capturar tecla física para este mapeamento\n(pressione a tecla desejada; Esc cancela)")
        self._lbl_map_key = ctk.CTkLabel(p, text="(nenhuma)",
                                         text_color="#e74c3c",
                                         font=FONT_BOLD,
                                         fg_color=KEY_BADGE_BG, corner_radius=6,
                                         border_width=1, border_color=BADGE_BORDER,
                                         width=90, height=28)
        self._lbl_map_key.grid(row=1, column=2, sticky="w", padx=(12, 6))

        # Tipo (linha 2)
        ctk.CTkLabel(p, text="Tipo de ação:", font=FONT_NORMAL).grid(row=2, column=0, sticky="e", padx=(12, 6), pady=6)
        disp_to_kind = dict(TYPE_OPTIONS)
        kind_to_disp = {v: k for k, v in TYPE_OPTIONS}
        self._menus = {}
        self._menus["type"] = ctk.CTkOptionMenu(
            p, values=list(disp_to_kind.keys()), width=200,
            command=lambda _v: self._on_type_changed(),
        )
        self._menus["type"].grid(row=2, column=1, sticky="w", pady=6)
        CTkToolTip(self._menus["type"], "Tipo de mensagem MIDI a enviar:\n• CC alternar: liga/desliga a cada pressão\n• CC momentâneo: segura=ON, solta=OFF\n• Nota: Note On ao pressionar, Note Off ao soltar\n• Program Change: troca de preset")

        # Canal (linha 3)
        ctk.CTkLabel(p, text="Canal MIDI:", font=FONT_NORMAL).grid(row=3, column=0, sticky="e", padx=(12, 6), pady=6)
        self._menus["channel"] = ctk.CTkOptionMenu(
            p, values=[str(c) for c in range(1, 17)], width=70,
            command=lambda _v: self._commit_from_panel(),
        )
        self._menus["channel"].grid(row=3, column=1, sticky="w", pady=6)
        CTkToolTip(self._menus["channel"], "Canal MIDI (1–16)\nDeve coincidir com o canal do plugin/DAW")

        # Preenche frames por tipo com os campos dinâmicos
        self._entries: dict[str, ctk.CTkEntry] = {}
        self._build_type_frames()

        # Aviso e rodapé (linhas gerenciadas dinamicamente)
        self._warn_lbl = ctk.CTkLabel(p, text="", text_color="#e67e22", font=FONT_SMALL)
        self._warn_lbl.grid(row=99, column=0, columnspan=5, sticky="w", padx=12, pady=(2, 8))
        ctk.CTkLabel(p, text="Alterações aplicam e salvam automaticamente.",
                     text_color="#7f8c8d", font=FONT_SMALL).grid(row=100, column=0, columnspan=5,
                                                sticky="w", padx=12, pady=(0, 10))

    def _build_type_frames(self) -> None:
        """Cria os campos numéricos dentro de cada frame por tipo."""
        # cc_toggle
        f = self._type_frames["cc_toggle"]
        f.grid_columnconfigure(1, weight=0)
        f.grid_columnconfigure(3, weight=0)
        self._num_field_in_frame(f, 0, 0, "CC:", "cc", "Número do controlador CC (0–127)")
        self._num_field_in_frame(f, 1, 0, "Valor ON:", "on_value", "Valor enviado ao ligar (0–127, padrão 127)")
        self._num_field_in_frame(f, 1, 2, "Valor OFF:", "off_value", "Valor enviado ao desligar (0–127, padrão 0)")

        # cc_momentary
        f = self._type_frames["cc_momentary"]
        f.grid_columnconfigure(1, weight=0)
        f.grid_columnconfigure(3, weight=0)
        self._num_field_in_frame(f, 0, 0, "CC:", "cc", "Número do controlador CC (0–127)")
        self._num_field_in_frame(f, 1, 0, "Ao pressionar:", "press_value", "Valor enquanto a tecla está pressionada (0–127)")
        self._num_field_in_frame(f, 1, 2, "Ao soltar:", "release_value", "Valor ao soltar a tecla (0–127, padrão 0)")

        # note
        f = self._type_frames["note"]
        f.grid_columnconfigure(1, weight=0)
        f.grid_columnconfigure(3, weight=0)
        self._num_field_in_frame(f, 0, 0, "Nota:", "note", "Número da nota MIDI (0–127, ex.: 60 = C4)")
        self._num_field_in_frame(f, 0, 2, "Velocidade:", "velocity", "Velocidade da nota (0–127, padrão 100)")

        # pc
        f = self._type_frames["pc"]
        f.grid_columnconfigure(1, weight=0)
        self._num_field_in_frame(f, 0, 0, "Programa:", "program", "Número do programa (0–127)")

    def _num_field_in_frame(self, frame: ctk.CTkFrame, row: int, col: int, label: str, name: str, tooltip: str = "") -> None:
        ctk.CTkLabel(frame, text=label, font=FONT_NORMAL).grid(row=row, column=col, sticky="e", padx=(12, 6), pady=6)
        entry = ctk.CTkEntry(frame, width=70, justify="center")
        entry.bind("<FocusOut>", lambda _e, n=name: self._commit_from_panel())
        entry.bind("<Return>", lambda _e, n=name: self._commit_from_panel())
        entry.grid(row=row, column=col + 1, sticky="w", pady=6)
        if tooltip:
            CTkToolTip(entry, tooltip)
        self._entries[name] = entry

# ==================================================================
    # Lista de teclas mapeadas (virtualizada: recicla widgets)
    # ==================================================================

    def _rebuild_list(self) -> None:
        self._cancel_pending_delete()

        # Esconde widgets órfãos (índices que não existem mais)
        for idx in list(self._row_widgets.keys()):
            if idx >= len(self._cfg.mappings):
                row, btn, del_btn = self._row_widgets.pop(idx)
                row.grid_remove()
                self._row_pool.append((row, btn, del_btn))

        if not self._cfg.mappings:
            # Mostra placeholder vazio
            self._show_empty_placeholder()
            return

        self._hide_empty_placeholder()
        self._delete_buttons = {}

        # Atualiza/cria linhas para cada mapeamento
        for i, m in enumerate(self._cfg.mappings):
            self._update_or_create_row(i, m)

        # Ajusta seleção visual
        self._update_selection_colors()

    def _show_empty_placeholder(self) -> None:
        if not hasattr(self, "_empty_label") or self._empty_label is None:
            self._empty_label = ctk.CTkLabel(
                self._list_frame,
                text='Nenhuma tecla mapeada — use "+ Adicionar tecla".',
                text_color="#7f8c8d",
                font=FONT_NORMAL,
            )
        self._empty_label.grid(row=0, column=0, pady=20)

    def _hide_empty_placeholder(self) -> None:
        if hasattr(self, "_empty_label") and self._empty_label is not None:
            self._empty_label.grid_remove()

    def _get_or_create_row(self) -> tuple[ctk.CTkFrame, ctk.CTkButton, ctk.CTkButton]:
        if self._row_pool:
            return self._row_pool.pop()
        row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
        row.grid_columnconfigure(0, weight=1)

        btn = ctk.CTkButton(
            row, text="", anchor="w", height=30,
            fg_color=ROW_BG, hover_color=ROW_HOVER,
            command=lambda: None,  # placeholder, setado em _update_or_create_row
        )
        btn.grid(row=0, column=0, sticky="ew")

        del_btn = ctk.CTkButton(
            row, text="✕", width=30, height=30,
            fg_color="#7b241c", hover_color="#943126",
            command=lambda: None,  # placeholder
        )
        del_btn.grid(row=0, column=1, padx=(6, 0))
        return row, btn, del_btn

    def _update_or_create_row(self, idx: int, m: Mapping) -> None:
        key_disp = m.key.upper() if m.key else "(defina a tecla)"
        summary = f"{key_disp}  →  {describe_action(m.action)}"
        selected = (idx == self._selected)

        if idx in self._row_widgets:
            row, btn, del_btn = self._row_widgets[idx]
            row.grid(row=idx, column=0, sticky="ew", pady=2, padx=2)
        else:
            row, btn, del_btn = self._get_or_create_row()
            row.grid(row=idx, column=0, sticky="ew", pady=2, padx=2)
            self._row_widgets[idx] = (row, btn, del_btn)

        btn.configure(
            text=summary,
            fg_color=ROW_SEL_BG if selected else ROW_BG,
            hover_color=ROW_SEL_BG if selected else ROW_HOVER,
            command=lambda i=idx: self._select_mapping(i),
        )
        del_btn.configure(
            command=lambda i=idx: self._remove_mapping(i),
        )
        self._delete_buttons[idx] = del_btn

    def _update_selection_colors(self) -> None:
        for idx, (row, btn, del_btn) in self._row_widgets.items():
            selected = (idx == self._selected)
            btn.configure(
                fg_color=ROW_SEL_BG if selected else ROW_BG,
                hover_color=ROW_SEL_BG if selected else ROW_HOVER,
            )

    # ------------------------------------------------------------------
    # Exclusão em dois cliques (✕ vira "Certeza?"; segundo clique apaga)
    # ------------------------------------------------------------------

    def _remove_mapping(self, idx: int) -> None:
        if not (0 <= idx < len(self._cfg.mappings)):
            return
        self.focus_set()  # evita Espaço/Enter reativar o botão ✕ focado
        if self._pending_delete != idx:
            self._cancel_pending_delete()
            self._pending_delete = idx
            btn = self._delete_buttons.get(idx)
            if btn is not None:
                btn.configure(text="Certeza?", width=76, fg_color="#c0392b",
                              hover_color="#e74c3c")
            self._pending_delete_after = self.after(2500, self._cancel_pending_delete)
            return

        self._cancel_pending_delete()
        del self._cfg.mappings[idx]

        # Remove o widget do índice deletado e devolve ao pool
        if idx in self._row_widgets:
            row, btn, del_btn = self._row_widgets.pop(idx)
            row.grid_remove()
            self._row_pool.append((row, btn, del_btn))

        # Desloca widgets dos índices maiores para baixo
        for i in range(idx, len(self._cfg.mappings)):
            if i + 1 in self._row_widgets:
                row, btn, del_btn = self._row_widgets.pop(i + 1)
                row.grid(row=i, column=0, sticky="ew", pady=2, padx=2)
                btn.configure(command=lambda j=i: self._select_mapping(j))
                del_btn.configure(command=lambda j=i: self._remove_mapping(j))
                self._row_widgets[i] = (row, btn, del_btn)
                self._delete_buttons[i] = del_btn

        # Limpa o último índice que sobrou (se houver)
        last_idx = len(self._cfg.mappings)
        if last_idx in self._row_widgets:
            row, btn, del_btn = self._row_widgets.pop(last_idx)
            row.grid_remove()
            self._row_pool.append((row, btn, del_btn))

        if self._selected == idx:
            self._selected = None
            self._rebuild_edit_panel()
        elif self._selected is not None and self._selected > idx:
            self._selected -= 1

        self._update_selection_colors()
        if not self._cfg.mappings:
            self._show_empty_placeholder()
        self._commit(rebuild_list=False)

    def _cancel_pending_delete(self) -> None:
        if self._pending_delete_after is not None:
            try:
                self.after_cancel(self._pending_delete_after)
            except Exception:
                pass
            self._pending_delete_after = None
        if getattr(self, "_pending_delete", None) is not None:
            btn = self._delete_buttons.get(self._pending_delete)
            if btn is not None:
                try:
                    btn.configure(text="✕", width=30, fg_color="#7b241c",
                                  hover_color="#943126")
                except Exception:
                    pass
        self._pending_delete = None

    def _select_mapping(self, idx: int) -> None:
        if idx == self._selected:
            return
        self._selected = idx
        self._update_selection_colors()
        self._rebuild_edit_panel()

    def _focused_widget_name(self) -> str:
        name = getattr(self.focus_get(), "winfo_name", "")
        if callable(name):
            name = name()
        return str(name or "").lower()

    def _move_selection(self, delta: int) -> str:
        if "entry" in self._focused_widget_name() or self._capturing is not None:
            return ""  # não rouba ↑/↓ de campos de texto nem durante captura
        n = len(self._cfg.mappings)
        if n == 0:
            return "break"
        cur = -1 if self._selected is None else self._selected
        self._select_mapping(max(0, min(n - 1, cur + delta)))
        return "break"

    def _on_delete_key(self, _event=None) -> str:
        if "entry" in self._focused_widget_name() or self._capturing is not None:
            return ""
        if self._selected is not None:
            self._remove_mapping(self._selected)  # 1º Del marca; 2º apaga
        return "break"

    def _add_mapping(self) -> None:
        # Reutiliza uma entrada ainda sem tecla, se houver (evita duplicar
        # em cliques repetidos / Espaço com botão focado e limpa resquícios).
        for i, m in enumerate(self._cfg.mappings):
            if m.key == "":
                self._selected = i
                self._update_selection_colors()
                break
        else:
            self._cfg.mappings.append(Mapping(key="", action=CCToggleAction()))
            self._selected = len(self._cfg.mappings) - 1
            self._commit(rebuild_list=True)
        self._rebuild_edit_panel()
        self._start_capture_map_key()  # já entra em modo captura

    # ==================================================================
    # Painel de edição (show/hide por tipo)
    # ==================================================================

    def _rebuild_edit_panel(self) -> None:
        """Atualiza o painel conforme a seleção atual (não reconstrói widgets)."""
        # Esconde todos os frames de tipo
        for f in self._type_frames.values():
            f.grid_remove()

        if self._selected is None or not (0 <= self._selected < len(self._cfg.mappings)):
            self._edit_title.configure(text="Selecione uma tecla na lista ou adicione uma nova.")
            self._lbl_map_key.configure(text="(nenhuma)", text_color="#e74c3c")
            self._menus["type"].set("CC alternar (toggle)")
            self._menus["channel"].set("1")
            self._clear_entries()
            return

        m = self._cfg.mappings[self._selected]
        a = m.action

        # Atualiza widgets estáticos
        self._edit_title.configure(text=f"Editando tecla {self._selected + 1}")
        self._lbl_map_key.configure(text=m.key.upper() if m.key else "(nenhuma)",
                                    text_color="#f1c40f" if m.key else "#e74c3c")
        kind_to_disp = {v: k for k, v in TYPE_OPTIONS}
        self._menus["type"].set(kind_to_disp[a.kind])
        self._menus["channel"].set(str(a.channel + 1))

        # Preenche entries com valores atuais
        self._fill_entries(a)

        # Mostra frame do tipo atual
        self._type_frames[a.kind].grid()

        self._set_warn("")

    def _clear_entries(self) -> None:
        for entry in self._entries.values():
            entry.delete(0, "end")

    def _fill_entries(self, action: Action) -> None:
        self._clear_entries()
        if action.kind in ("cc_toggle", "cc_momentary"):
            self._entries["cc"].insert(0, str(action.cc))
            if action.kind == "cc_toggle":
                self._entries["on_value"].insert(0, str(action.on_value))
                self._entries["off_value"].insert(0, str(action.off_value))
            else:
                self._entries["press_value"].insert(0, str(action.press_value))
                self._entries["release_value"].insert(0, str(action.release_value))
        elif action.kind == "note":
            self._entries["note"].insert(0, str(action.note))
            self._entries["velocity"].insert(0, str(action.velocity))
        elif action.kind == "pc":
            self._entries["program"].insert(0, str(action.program))

    def _on_type_changed(self) -> None:
        if self._read_panel_into():
            # Apenas troca o frame visível, não reconstrói o painel
            kind = dict(TYPE_OPTIONS)[self._menus["type"].get()]
            for k, f in self._type_frames.items():
                if k == kind:
                    f.grid()
                else:
                    f.grid_remove()
            # Preenche entries do novo tipo com valores padrão
            self._fill_default_entries(kind)
            self._commit(rebuild_list=True)

    def _fill_default_entries(self, kind: str) -> None:
        self._clear_entries()
        if kind in ("cc_toggle", "cc_momentary"):
            self._entries["cc"].insert(0, "0")
            if kind == "cc_toggle":
                self._entries["on_value"].insert(0, "127")
                self._entries["off_value"].insert(0, "0")
            else:
                self._entries["press_value"].insert(0, "127")
                self._entries["release_value"].insert(0, "0")
        elif kind == "note":
            self._entries["note"].insert(0, "60")
            self._entries["velocity"].insert(0, "100")
        elif kind == "pc":
            self._entries["program"].insert(0, "0")

    def _read_panel_into(self) -> bool:
        """Copia o estado do painel para self.cfg. False se inválido."""
        if self._selected is None or not (0 <= self._selected < len(self._cfg.mappings)):
            return False
        old = self._cfg.mappings[self._selected]

        kind = dict(TYPE_OPTIONS)[self._menus["type"].get()]  # rótulo -> kind
        channel = int(self._menus["channel"].get()) - 1
        vals = {}
        clamped: list[str] = []
        for name, lo_hi in (("cc", (0, 127)), ("on_value", (0, 127)), ("off_value", (0, 127)),
                            ("press_value", (0, 127)), ("release_value", (0, 127)),
                            ("note", (0, 127)), ("velocity", (0, 127)), ("program", (0, 127))):
            ent = self._entries.get(name)
            if ent is None:
                continue
            raw = ent.get().strip()
            try:
                orig = int(raw)
                v = max(lo_hi[0], min(lo_hi[1], orig))
            except ValueError:
                self._set_warn(f"Valor inválido em '{name}'. Use um inteiro.")
                return False
            if v != orig:
                clamped.append(f"{name}: {orig} → {v}")
            vals[name] = v

        if kind == "cc_toggle":
            act = CCToggleAction(channel, vals.get("cc", 0),
                                 vals.get("on_value", 127), vals.get("off_value", 0))
        elif kind == "cc_momentary":
            act = CCMomentaryAction(channel, vals.get("cc", 0),
                                    vals.get("press_value", 127), vals.get("release_value", 0))
        elif kind == "note":
            act = NoteAction(channel, vals.get("note", 60), vals.get("velocity", 100))
        else:
            act = PCAction(channel, vals.get("program", 0))

        self._cfg.mappings[self._selected] = Mapping(key=old.key, action=act)
        if clamped:
            self._set_warn("Ajustado ao limite MIDI (0–127): " + ", ".join(clamped))
        else:
            self._set_warn("")
        return True

    def _commit_from_panel(self) -> None:
        if not self._read_panel_into():
            return
        # Debounce: cancela timer anterior e agenda novo
        if self._debounce_after is not None:
            try:
                self.after_cancel(self._debounce_after)
            except Exception:
                pass
        self._debounce_after = self.after(300, lambda: self._commit(rebuild_list=True))

    def _set_warn(self, msg: str) -> None:
        try:
            self._warn_lbl.configure(text=msg)
        except Exception:
            pass

    # ==================================================================
    # Captura física de tecla
    # ==================================================================

    def _start_capture_map_key(self) -> None:
        if self._selected is None:
            return
        self._capturing = ("mapping", self._selected)
        self._btn_map_key.configure(text="⏺ Capturando…", fg_color=ACCENT)
        self._set_warn("aperte uma tecla — Esc cancela")
        self.focus_set()  # tira o foco de botões/entries (Espaço não dispara nada)
        self.bind("<KeyPress>", self._on_capture_keypress)
        self.bind("<FocusOut>", self._on_focus_out)

    def _start_capture_toggle_key(self) -> None:
        self._capturing = ("toggle", None)
        self._btn_trig_cap.configure(text="⏺ Capturando…", fg_color=ACCENT)
        self._lbl_trig_hint.configure(text="aperte uma tecla — Esc cancela")
        self.focus_set()
        self.bind("<KeyPress>", self._on_capture_keypress)
        self.bind("<FocusOut>", self._on_focus_out)

    def _on_focus_out(self, _event=None) -> str:
        # O bind no toplevel também borbuja FocusOut de transições INTERNAS
        # (ex.: o próprio focus_set disparado pelo clique no botão). Decide
        # depois que o foco assenta: só desiste se nenhum widget do app ficou
        # com ele — i.e., o usuário foi para outra janela de verdade.
        self.after_idle(self._maybe_cancel_capture)
        return ""

    def _maybe_cancel_capture(self) -> None:
        if self._capturing is None:
            return
        try:
            focused = self.focus_get()
        except Exception:
            focused = None
        if focused is None:
            self._cancel_capture()

    def _cancel_capture(self) -> None:
        self._capturing = None
        for seq in ("<KeyPress>", "<FocusOut>"):
            try:
                self.unbind(seq)
            except Exception:
                pass
        self._btn_map_key.configure(text="Capturar tecla", fg_color=BTN_SECONDARY,
                                    hover_color=BTN_SECONDARY_HOVER)
        self._btn_trig_cap.configure(text="Capturar tecla", fg_color=BTN_SECONDARY,
                                     hover_color=BTN_SECONDARY_HOVER)
        try:
            self._lbl_trig_hint.configure(text="")
        except AttributeError:
            pass  # painel reconstruído durante a captura
        self._set_warn("")

    def _on_capture_keypress(self, event) -> str:
        if self._capturing is None:
            return ""
        widget = str(getattr(event, "widget", "") or "")
        if "entry" in widget.lower():
            return ""  # usuário digitando num campo — não é captura
        ks = event.keysym
        if ks in ("Shift_L", "Shift_R", "Control_L", "Control_R",
                  "Alt_L", "Alt_R", "Win_L", "Win_R"):
            return "break"  # ignora modificador puro; espera a tecla de verdade
        if ks == "Escape":
            self._cancel_capture()
            return "break"
        name = tk_keysym_to_name(ks)
        target, idx = self._capturing
        self._cancel_capture()

        if target == "mapping":
            if normalize_key(self._cfg.toggle_key) == name:
                self._set_warn(
                    f"'{name.upper()}' é a tecla da interceptação — escolha outra."
                )
                return "break"
            other = self._cfg.has_key(name, exclude_index=idx)
            if other:
                self._set_warn(f"A tecla '{name.upper()}' já está mapeada.")
                return "break"
            self._set_warn("")
            old = self._cfg.mappings[idx]
            self._cfg.mappings[idx] = Mapping(key=name, action=old.action)
            self._lbl_map_key.configure(text=name.upper(), text_color="#f1c40f")
        else:
            if self._cfg.has_key(name):
                self._set_warn(
                    f"'{name.upper()}' já está mapeada a uma tecla — o gatilho precisa ser exclusivo."
                )
                return "break"
            self._set_warn("")
            self._cfg.toggle_key = name
            self._lbl_trig_val.configure(text=name.upper(), text_color="#f1c40f")

        self._commit(rebuild_list=True)
        return "break"

    # ==================================================================
    # Porta MIDI / modo captura
    # ==================================================================

    def _refresh_ports(self, select: str | None = None) -> None:
        ports = self._engine.list_ports()
        values = ports if ports else ["(sem portas)"]
        self._port_menu.configure(values=values)
        chosen = select if select in ports else (ports[0] if ports else "(sem portas)")
        self._port_menu.set(chosen)

    def _refresh_ports_clicked(self) -> None:
        self._refresh_ports(select=self._port_menu.get())

    def _on_port_selected(self, name: str) -> None:
        if name.startswith("("):
            return
        self._cfg.midi_port = name
        self._commit(rebuild_list=False)

    def _toggle_capture_clicked(self) -> None:
        self._engine.toggle_capture()

    # ==================================================================
    # Persistência / aplicação
    # ==================================================================

    def _commit(self, *, rebuild_list: bool) -> None:
        """Salva o arquivo principal e aplica na engine."""
        try:
            cfgmod.validate(self._cfg)
        except cfgmod.ConfigError as e:
            mb.showwarning("Configuração inválida", str(e), parent=self)
            return
        try:
            cfgmod.save(self._cfg_path, self._cfg)
        except OSError as e:
            mb.showerror("Erro ao salvar", f"Não foi possível salvar {self._cfg_path}:\n{e}", parent=self)
            return
        self._engine.apply_config(self._cfg)
        if rebuild_list:
            self._rebuild_list()

    # ------------------------------------------------------------------
    # Exportar / Importar
    # ------------------------------------------------------------------

    def _export(self) -> None:
        path = fd.asksaveasfilename(
            title="Exportar mapeamento",
            defaultextension=".toml",
            filetypes=[("Mapeamento TOML", "*.toml")],
            initialfile="mapeamento.toml",
        )
        if not path:
            return
        try:
            cfgmod.save(path, self._cfg)
            self._engine.push_event(f"Mapeamento exportado: {path}")
        except OSError as e:
            mb.showerror("Erro ao exportar", str(e), parent=self)

    def _import(self) -> None:
        self._cancel_capture()  # captura pendente apontaria para índice do arquivo antigo
        if not mb.askyesno(
            "Importar mapeamento",
            "Importar vai SUBSTITUIR o mapeamento atual, além da porta MIDI e da\n"
            "tecla de interceptação gravadas no arquivo (o arquivo importado não é alterado).\n"
            "Continuar?",
            parent=self,
        ):
            return
        path = fd.askopenfilename(
            title="Importar mapeamento",
            filetypes=[("Mapeamento TOML", "*.toml"), ("Todos os arquivos", "*.*")],
        )
        if not path:
            return
        try:
            loaded = cfgmod.load(path)
        except (cfgmod.ConfigError, OSError) as e:
            mb.showerror("Erro ao importar", str(e), parent=self)
            return

        self._cfg = loaded
        self._selected = None
        self._commit(rebuild_list=True)
        self._rebuild_edit_panel()
        self._refresh_ports(select=self._cfg.midi_port)
        self._lbl_trig_val.configure(text=(self._cfg.toggle_key or "(desativado)").upper(),
                                     text_color="#f1c40f" if self._cfg.toggle_key else "#e74c3c")

    # ==================================================================
    # Polling: monitor + status
    # ==================================================================

    def _poll(self) -> None:
        # Drena eventos da engine para o monitor (mais novo no topo)
        new_events = []
        while self._engine.events:
            new_events.append(self._engine.events.pop())
        if new_events:
            self._monitor.configure(state="normal")
            for ev in new_events:
                if "⚠" in ev or "ERRO" in ev:
                    self._monitor.insert("1.0", ev + "\n", "err")
                else:
                    self._monitor.insert("1.0", ev + "\n")
            self._trim_monitor()
            self._monitor.configure(state="disabled")

        self._reflect_state()
        self.after(150, self._poll)

    def _reflect_state(self) -> None:
        """Estado da interceptação e da porta — título, rótulos, botão."""
        active = self._engine.capture_active()
        self.title(f"{BASE_TITLE}  [INTERCEPTANDO]" if active else BASE_TITLE)
        self._lbl_mode.configure(
            text=f"Interceptação: {'ATIVA' if active else 'INATIVA'}",
            text_color="#2ecc71" if active else "#95a5a6",
        )
        self._btn_capture.configure(
            text=("■ Desativar interceptação" if active else "▶ Ativar interceptação agora"),
            fg_color="#7b241c" if active else ACCENT,
        )
        if self._capturing is None:
            hk_ok = self._engine.toggle_hotkey_ok()
            self._lbl_trig_hint.configure(
                text="" if hk_ok else
                "⚠ esta tecla não existe/está indisponível aqui "
                "(comum em notebooks) — clique em 'Capturar tecla' e escolha outra",
                text_color="#e67e22",
            )

        pname = self._engine.port_name()
        if pname is None:
            self._port_status.configure(text="● desconectado", text_color="#c0392b")
        else:
            self._port_status.configure(text=f"● {pname}", text_color="#2ecc71")

    def _clear_monitor(self) -> None:
        self._monitor.configure(state="normal")
        self._monitor.delete("1.0", "end")
        self._monitor.configure(state="disabled")

    def _trim_monitor(self) -> None:
        lines = int(self._monitor.index("end-1c").split(".")[0])
        if lines > 50:
            self._monitor.delete("51.0", "end")

    # ==================================================================
    # Ciclo de vida
    # ==================================================================

    def _on_close(self) -> None:
        # Flush debounce timer
        if self._debounce_after is not None:
            try:
                self.after_cancel(self._debounce_after)
                self._commit(rebuild_list=True)
            except Exception:
                pass

        try:
            self._commit_from_panel()  # salva qualquer edição pendente
        except Exception:
            pass
        # Salva geometria da janela
        try:
            geo = self.geometry()  # "WxH+X+Y"
            if "+" in geo:
                wh, x, y = geo.split("+")
                w, h = wh.split("x")
                self._cfg.window_x = int(x)
                self._cfg.window_y = int(y)
                self._cfg.window_w = int(w)
                self._cfg.window_h = int(h)
                cfgmod.save(self._cfg_path, self._cfg)
        except Exception:
            pass
        self._engine.stop()
        self.destroy()
