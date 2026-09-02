"""Stubs headless de tkinter/customtkinter/keyboard para os testes.

`install()` substitui os módulos reais em sys.modules ANTES de qualquer
import de `midi_qwerty.*`. Os gravadores (KEYBOARD_HOOKS, WIDGET_KWARGS...)
permitem aos testes inspecionar o que a aplicação criou/hookou.
"""

import sys
import types
from unittest.mock import DEFAULT, MagicMock

# --- gravadores -------------------------------------------------------------

KEYBOARD_HOOKS: dict[str, object] = {}   # tecla -> callback passada a hook_key
KEYBOARD_HOTKEYS: list[str] = []         # teclas passadas a add_hotkey
WIDGET_KWARGS: dict[str, list[dict]] = {}  # classe -> kwargs dos __init__


def list_widget_texts(*class_names: str) -> list[str]:
    out: list[str] = []
    for cn in class_names:
        out.extend(str(k.get("text", "")) for k in WIDGET_KWARGS.get(cn, []))
    return out


# --- widgets ----------------------------------------------------------------


def _make_cls(name: str):
    class W:
        def __init__(self, *a, **k):
            object.__setattr__(self, "_mocks", {})
            self._mocks["configure"] = MagicMock(side_effect=self._do_configure)
            WIDGET_KWARGS.setdefault(name, []).append(k)

        def _do_configure(self, **kwargs):
            for key in ("text_color", "fg_color", "hover_color", "border_color"):
                if kwargs.get(key) == "":
                    raise ValueError(f"cor vazia inválida: {key}")
            if "text" in kwargs:
                WIDGET_KWARGS.setdefault(type(self).__name__, []).append(kwargs)

        def __getattr__(self, attr):
            m = self._mocks.get(attr)
            if m is None:
                if attr == "winfo_children":
                    m = lambda: []  # noqa: E731
                elif attr == "winfo_screenwidth":
                    m = lambda: 1920  # noqa: E731
                elif attr == "winfo_screenheight":
                    m = lambda: 1080  # noqa: E731
                elif attr in ("get", "index"):
                    m = lambda *a, **k: "1"  # noqa: E731
                elif attr == "configure":
                    m = self.configure  # noqa: E731
                else:
                    m = MagicMock()
                self._mocks[attr] = m
            return m

    W.__name__ = name
    return W


# --- instalação -------------------------------------------------------------


def install() -> None:
    tk = types.ModuleType("tkinter")
    tk_fd = types.ModuleType("tkinter.filedialog")
    tk_mb = types.ModuleType("tkinter.messagebox")
    tk.filedialog = tk_fd
    tk.messagebox = tk_mb
    for a in ("asksaveasfilename", "askopenfilename"):
        setattr(tk_fd, a, lambda **k: "")
    for a in ("askyesno", "showerror", "showwarning"):
        setattr(tk_mb, a, lambda *x, **k: True)
    sys.modules.update({
        "tkinter": tk,
        "tkinter.filedialog": tk_fd,
        "tkinter.messagebox": tk_mb,
    })

    ctk = types.ModuleType("customtkinter")
    for n in ("CTkFrame", "CTkLabel", "CTkButton", "CTkOptionMenu",
              "CTkScrollableFrame", "CTkTextbox", "CTkEntry"):
        setattr(ctk, n, _make_cls(n))

    class CTk(_make_cls("CTk")):
        def bind(self, *a, **k):
            pass

        def unbind(self, *a, **k):
            pass

        def focus_set(self):
            pass

    ctk.CTk = CTk
    ctk.CTkFont = lambda *a, **k: "font"
    ctk.set_appearance_mode = lambda *a: None
    ctk.set_default_color_theme = lambda *a: None
    sys.modules["customtkinter"] = ctk

    kb = types.ModuleType("keyboard")

    def hook_key(key, callback, suppress=False):
        KEYBOARD_HOOKS[key] = callback
        return key

    def unhook_key(key):
        KEYBOARD_HOOKS.pop(key, None)

    def add_hotkey(key, callback, **kwargs):
        KEYBOARD_HOTKEYS.append(key)
        return f"hotkey:{key}"

    def remove_hotkey(handle):
        k = str(handle).removeprefix("hotkey:")
        if k in KEYBOARD_HOTKEYS:
            KEYBOARD_HOTKEYS.remove(k)

    kb.hook_key = hook_key
    kb.unhook_key = unhook_key
    kb.add_hotkey = add_hotkey
    kb.remove_hotkey = remove_hotkey
    sys.modules["keyboard"] = kb
