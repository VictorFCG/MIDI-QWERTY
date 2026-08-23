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

import tkinter.filedialog as fd
import tkinter.messagebox as mb

import customtkinter as ctk

from . import config as cfgmod
from .config import (
    AppConfig,
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
ROW_SEL_BG = "#1f4e79"

TYPE_OPTIONS = [  # (rótulo exibido, kind)
    ("CC alternar (toggle)", "cc_toggle"),
    ("CC momentâneo", "cc_momentary"),
    ("Nota (note on/off)", "note"),
    ("Program Change", "pc"),
]

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


class MidiQwertyApp(ctk.CTk):
    def __init__(self, engine: Engine, cfg: AppConfig, cfg_path: str) -> None:
        super().__init__()
        self._engine = engine
        self._cfg = cfg
        self._cfg_path = cfg_path

        self._selected: int | None = None      # índice selecionado na lista
        self._capturing: tuple | None = None   # ("mapping", idx) | ("toggle", None)
        self._monitor_count = 0

        self.title("MIDI-QWERTY — teclado QWERTY → MIDI")
        self.geometry("1120x800")
        self.minsize(960, 700)
        ctk.set_appearance_mode("dark")

        self._build_ui()
        self._refresh_ports(select=cfg.midi_port)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Loop de atualização (monitor/status) — drena a fila da engine
        self.after(150, self._poll)

    # ==================================================================
    # Construção da UI
    # ==================================================================

    def _build_ui(self) -> None:
        # Layout fixo em duas colunas na área central:
        #   esquerda = lista de teclas (rolável) | direita = monitor
        # Só a linha central é flexível; painel de edição e barra do
        # gatilho têm altura estável (nada "salta" ao popular a lista).
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Linha 0: porta MIDI (largura total) ----------------------
        top = ctk.CTkFrame(self)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 6))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="Saída MIDI:").grid(row=0, column=0, padx=(10, 6), pady=10)
        self._port_menu = ctk.CTkOptionMenu(
            top, values=["(sem portas)"], width=320,
            command=self._on_port_selected,
        )
        self._port_menu.set("(sem portas)")
        self._port_menu.grid(row=0, column=1, sticky="w", pady=10)
        ctk.CTkButton(top, text="↻ Atualizar", width=90,
                      command=self._refresh_ports_clicked).grid(row=0, column=2, padx=6, pady=10)
        self._port_status = ctk.CTkLabel(top, text="● desconectado", text_color="#c0392b")
        self._port_status.grid(row=0, column=3, padx=(6, 12), pady=10)

        # --- Linha 1: centro — lista (esq.) + monitor (dir.) ----------
        center = ctk.CTkFrame(self, fg_color="transparent")
        center.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=12, pady=6)
        center.grid_columnconfigure(0, weight=3, uniform="cols")
        center.grid_columnconfigure(1, weight=2, uniform="cols")
        center.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(center, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 2))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="Teclas mapeadas (clique para editar):").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(head, text="Importar", width=90, fg_color="#5d6d7e",
                      hover_color="#717d7e", command=self._import).grid(row=0, column=1, padx=(0, 6))
        ctk.CTkButton(head, text="Exportar", width=90, fg_color="#5d6d7e",
                      hover_color="#717d7e", command=self._export).grid(row=0, column=2, padx=(0, 6))
        ctk.CTkButton(head, text="+ Adicionar tecla", width=140,
                      command=self._add_mapping).grid(row=0, column=3)

        self._list_frame = ctk.CTkScrollableFrame(center)
        self._list_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=2)
        self._list_frame.grid_columnconfigure(0, weight=1)

        right = ctk.CTkFrame(center, fg_color="transparent")
        right.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(6, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        mon_lbl = ctk.CTkLabel(right, text="Monitor de mensagens enviadas:", anchor="w")
        mon_lbl.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        self._monitor = ctk.CTkTextbox(right, state="disabled", wrap="none",
                                       font=ctk.CTkFont(family="Consolas", size=13))
        self._monitor.grid(row=1, column=0, sticky="nsew")

        # --- Linha 2: painel de edição (largura total) -----------------
        self._edit_panel = ctk.CTkFrame(self)
        self._edit_panel.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=6)
        self._edit_panel.grid_columnconfigure(1, weight=1)

        # --- Linha 3: gatilho + modo captura (altura fixa) --------------
        bottom = ctk.CTkFrame(self)
        bottom.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(6, 12))
        bottom.grid_columnconfigure(0, weight=1)

        trig = ctk.CTkFrame(bottom, fg_color="transparent")
        trig.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        ctk.CTkLabel(trig, text="Tecla gatilho do modo captura:").pack(side="left")
        self._btn_trig_cap = ctk.CTkButton(trig, text="Capturar tecla", width=110,
                                           command=self._start_capture_toggle_key)
        self._btn_trig_cap.pack(side="left", padx=8)
        self._lbl_trig_val = ctk.CTkLabel(trig, text=self._cfg.toggle_key or "(desativado)",
                                          text_color="#f1c40f")
        self._lbl_trig_val.pack(side="left")
        self._lbl_trig_hint = ctk.CTkLabel(trig, text="", text_color="#e67e22")
        self._lbl_trig_hint.pack(side="left")

        ctl = ctk.CTkFrame(bottom, fg_color="transparent")
        ctl.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        self._btn_capture = ctk.CTkButton(ctl, text="▶ Ativar modo captura agora",
                                          width=220, command=self._toggle_capture_clicked)
        self._btn_capture.pack(side="left")
        self._lbl_mode = ctk.CTkLabel(ctl, text="Modo captura: INATIVO",
                                      text_color="#95a5a6", font=ctk.CTkFont(weight="bold"))
        self._lbl_mode.pack(side="left", padx=16)

        self._rebuild_list()
        self._rebuild_edit_panel()

    # ==================================================================
    # Lista de teclas mapeadas
    # ==================================================================

    def _rebuild_list(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        for i, m in enumerate(self._cfg.mappings):
            key_disp = m.key.upper() if m.key else "(defina a tecla)"
            summary = f"{key_disp}  →  {describe_action(m.action)}"
            selected = (i == self._selected)

            row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", pady=2, padx=2)
            row.grid_columnconfigure(0, weight=1)

            btn = ctk.CTkButton(
                row, text=summary, anchor="w", height=30,
                fg_color=ROW_SEL_BG if selected else ROW_BG,
                hover_color=ROW_SEL_BG,
                command=lambda idx=i: self._select_mapping(idx),
            )
            btn.grid(row=0, column=0, sticky="ew")

            dele = ctk.CTkButton(row, text="✕", width=30, height=30,
                                 fg_color="#7b241c", hover_color="#943126",
                                 command=lambda idx=i: self._remove_mapping(idx))
            dele.grid(row=0, column=1, padx=(6, 0))

    def _select_mapping(self, idx: int) -> None:
        self._selected = idx
        self._rebuild_list()
        self._rebuild_edit_panel()

    def _add_mapping(self) -> None:
        # Reutiliza uma entrada ainda sem tecla, se houver (evita duplicar
        # em cliques repetidos / Espaço com botão focado e limpa resquícios).
        for i, m in enumerate(self._cfg.mappings):
            if m.key == "":
                self._selected = i
                break
        else:
            self._cfg.mappings.append(Mapping(key="", action=CCToggleAction()))
            self._selected = len(self._cfg.mappings) - 1
            self._commit(rebuild_list=True)
        self._rebuild_edit_panel()
        self._start_capture_map_key()  # já entra em modo captura

    def _remove_mapping(self, idx: int) -> None:
        if not (0 <= idx < len(self._cfg.mappings)):
            return
        self.focus_set()  # evita Espaço/Enter reativar o botão ✕ focado
        del self._cfg.mappings[idx]
        if self._selected == idx:
            self._selected = None
            self._rebuild_edit_panel()
        elif self._selected is not None and self._selected > idx:
            self._selected -= 1
        self._commit(rebuild_list=True)

    # ==================================================================
    # Painel de edição
    # ==================================================================

    def _rebuild_edit_panel(self) -> None:
        """Redesenha o painel conforme a seleção atual."""
        for w in self._edit_panel.winfo_children():
            w.destroy()
        self._entries: dict[str, ctk.CTkEntry] = {}
        self._menus: dict[str, ctk.CTkOptionMenu] = {}

        if self._selected is None or not (0 <= self._selected < len(self._cfg.mappings)):
            ctk.CTkLabel(self._edit_panel, text="Selecione uma tecla na lista ou adicione uma nova.",
                         text_color="#7f8c8d").grid(row=0, column=0, sticky="w", padx=12, pady=14)
            return

        m = self._cfg.mappings[self._selected]
        p = self._edit_panel
        title = f"Editando tecla {self._selected + 1}"
        ctk.CTkLabel(p, text=title, font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#7f8c8d").grid(row=0, column=0, columnspan=4, sticky="w",
                                                padx=12, pady=(8, 0))

        # Tecla ---------------------------------------------------------
        ctk.CTkLabel(p, text="Tecla:").grid(row=1, column=0, sticky="e", padx=(12, 6), pady=6)
        self._btn_map_key = ctk.CTkButton(p, text="🎹 Capturar", width=110,
                                          command=self._start_capture_map_key)
        self._btn_map_key.grid(row=1, column=1, sticky="w", pady=6)
        self._lbl_map_key = ctk.CTkLabel(p, text=m.key.upper() if m.key else "(nenhuma)",
                                         text_color="#f1c40f" if m.key else "#c0392b",
                                         font=ctk.CTkFont(weight="bold"))
        self._lbl_map_key.grid(row=1, column=1, sticky="w", padx=(130, 0))
        self._lbl_map_hint = ctk.CTkLabel(p, text="", text_color="#e67e22")
        self._lbl_map_hint.grid(row=1, column=2, columnspan=2, sticky="w", padx=(12, 6))

        # Tipo ----------------------------------------------------------
        ctk.CTkLabel(p, text="Tipo de ação:").grid(row=2, column=0, sticky="e", padx=(12, 6), pady=6)
        disp_to_kind = dict(TYPE_OPTIONS)
        kind_to_disp = {v: k for k, v in TYPE_OPTIONS}
        self._menus["type"] = ctk.CTkOptionMenu(
            p, values=list(disp_to_kind.keys()), width=200,
            command=lambda _v: self._on_type_changed(),
        )
        self._menus["type"].set(kind_to_disp[m.action.kind])
        self._menus["type"].grid(row=2, column=1, sticky="w", pady=6)

        # Canal (exibido 1..16, armazenado 0..15) ------------------------
        ctk.CTkLabel(p, text="Canal MIDI:").grid(row=3, column=0, sticky="e", padx=(12, 6), pady=6)
        self._menus["channel"] = ctk.CTkOptionMenu(
            p, values=[str(c) for c in range(1, 17)], width=70,
            command=lambda _v: self._commit_from_panel(),
        )
        self._menus["channel"].set(str(m.action.channel + 1))
        self._menus["channel"].grid(row=3, column=1, sticky="w", pady=6)

        # Campos dinâmicos por tipo --------------------------------------
        a = m.action
        r = 4
        if a.kind in ("cc_toggle", "cc_momentary"):
            self._num_field(r, 0, "Número do CC:", "cc", a.cc)
            r += 1
            if a.kind == "cc_toggle":
                self._num_field(r, 0, "Valor ON:", "on_value", a.on_value)
                self._num_field(r, 2, "Valor OFF:", "off_value", a.off_value)
                r += 1
            else:
                self._num_field(r, 0, "Valor ao pressionar:", "press_value", a.press_value)
                self._num_field(r, 2, "Valor ao soltar:", "release_value", a.release_value)
                r += 1
        elif a.kind == "note":
            self._num_field(r, 0, "Número da nota (0–127):", "note", a.note)
            self._num_field(r, 2, "Velocidade (1–127):", "velocity", a.velocity)
            r += 1
        elif a.kind == "pc":
            self._num_field(r, 0, "Número do programa (0–127):", "program", a.program)
            r += 1

        self._warn_lbl = ctk.CTkLabel(p, text="", text_color="#e67e22")
        self._warn_lbl.grid(row=r, column=0, columnspan=4, sticky="w", padx=12, pady=(2, 8))
        ctk.CTkLabel(p, text="Alterações aplicam e salvam automaticamente.",
                     text_color="#7f8c8d").grid(row=r + 1, column=0, columnspan=4,
                                                sticky="w", padx=12, pady=(0, 10))

    def _num_field(self, row: int, col: int, label: str, name: str, value: int) -> None:
        p = self._edit_panel
        ctk.CTkLabel(p, text=label).grid(row=row, column=col, sticky="e", padx=(12, 6), pady=6)
        entry = ctk.CTkEntry(p, width=70, justify="center")
        entry.insert(0, str(value))
        entry.bind("<FocusOut>", lambda _e, n=name: self._commit_from_panel())
        entry.bind("<Return>", lambda _e, n=name: self._commit_from_panel())
        entry.grid(row=row, column=col + 1, sticky="w", pady=6)
        self._entries[name] = entry

    def _read_panel_into(self) -> bool:
        """Copia o estado do painel para self.cfg. False se inválido."""
        if self._selected is None or not (0 <= self._selected < len(self._cfg.mappings)):
            return False
        old = self._cfg.mappings[self._selected]

        kind = dict(TYPE_OPTIONS)[self._menus["type"].get()]  # rótulo -> kind
        channel = int(self._menus["channel"].get()) - 1
        vals = {}
        for name, lo_hi in (("cc", (0, 127)), ("on_value", (0, 127)), ("off_value", (0, 127)),
                            ("press_value", (0, 127)), ("release_value", (0, 127)),
                            ("note", (0, 127)), ("velocity", (0, 127)), ("program", (0, 127))):
            ent = self._entries.get(name)
            if ent is None:
                continue
            raw = ent.get().strip()
            try:
                v = max(lo_hi[0], min(lo_hi[1], int(raw)))
            except ValueError:
                self._set_warn(f"Valor inválido em '{name}'. Use um inteiro.")
                return False
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
        self._set_warn("")
        return True

    def _on_type_changed(self) -> None:
        if self._read_panel_into():
            self._rebuild_edit_panel()
            self._commit(rebuild_list=True)

    def _commit_from_panel(self) -> None:
        if self._read_panel_into():
            self._commit(rebuild_list=True)

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
        self._lbl_map_hint.configure(text="aperte uma tecla — Esc cancela")
        self.focus_set()  # tira o foco de botões/entries (Espaço não dispara nada)
        self.bind("<KeyPress>", self._on_capture_keypress)

    def _start_capture_toggle_key(self) -> None:
        self._capturing = ("toggle", None)
        self._btn_trig_cap.configure(text="⏺ Capturando…", fg_color=ACCENT)
        self._lbl_trig_hint.configure(text="aperte uma tecla — Esc cancela")
        self.focus_set()
        self.bind("<KeyPress>", self._on_capture_keypress)

    def _cancel_capture(self) -> None:
        self._capturing = None
        try:
            self.unbind("<KeyPress>")
        except Exception:
            pass
        self._btn_map_key.configure(text="🎹 Capturar", fg_color="transparent")
        self._btn_trig_cap.configure(text="Capturar tecla", fg_color="transparent")
        try:
            self._lbl_map_hint.configure(text="")
            self._lbl_trig_hint.configure(text="")
        except AttributeError:
            pass  # painel reconstruído durante a captura

    def _on_capture_keypress(self, event) -> str:
        if self._capturing is None:
            return ""
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
                    f"'{name.upper()}' é a tecla gatilho do modo captura — escolha outra."
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
            self._lbl_trig_val.configure(text=name, text_color="#f1c40f")

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
            "Importar vai SUBSTITUIR o mapeamento atual (o arquivo importado não é alterado).\nContinuar?",
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
        self._lbl_trig_val.configure(text=self._cfg.toggle_key or "(desativado)")

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
                self._monitor.insert("1.0", ev + "\n")
            self._trim_monitor()
            self._monitor.configure(state="disabled")

        # Status do modo captura
        active = self._engine.capture_active()
        self._lbl_mode.configure(
            text=f"Modo captura: {'ATIVO' if active else 'INATIVO'}",
            text_color="#2ecc71" if active else "#95a5a6",
        )
        self._btn_capture.configure(
            text=("■ Desativar modo captura" if active else "▶ Ativar modo captura agora"),
            fg_color="#7b241c" if active else ACCENT,
        )

        # Status da porta
        pname = self._engine.port_name()
        if pname is None:
            self._port_status.configure(text="● desconectado", text_color="#c0392b")
        else:
            self._port_status.configure(text=f"● {pname}", text_color="#2ecc71")

        self.after(150, self._poll)

    def _trim_monitor(self) -> None:
        lines = int(self._monitor.index("end-1c").split(".")[0])
        if lines > 50:
            self._monitor.delete("51.0", "end")

    # ==================================================================
    # Ciclo de vida
    # ==================================================================

    def _on_close(self) -> None:
        try:
            self._commit_from_panel()  # salva qualquer edição pendente
        except Exception:
            pass
        self._engine.stop()
        self.destroy()
