"""Regressão da GUI com CustomTkinter stubado (headless).

Porta para testes permanentes dos fluxos que antes eram verificados por
harnesses descartáveis: população inicial da lista, adicionar/capturar
tecla, colisões com a tecla gatilho, cancelamento por Esc, import durante
captura pendente, invariantes do layout fixo e trim do monitor.
"""

from fakes import WIDGET_KWARGS, list_widget_texts
from midi_qwerty.app import tk_keysym_to_name

TOML_1MAP = (
    '[midi]\nport = ""\n[capture]\ntoggle_key = "scroll lock"\n'
    '[[map]]\nkey = "f1"\ntype = "cc_toggle"\nchannel = 0\ncc = 20\n'
    "on_value = 127\noff_value = 0\n"
)

TOML_3MAPS = TOML_1MAP.replace("\n", "\n") + (
    '[[map]]\nkey = "f2"\ntype = "note"\nchannel = 0\nnote = 60\nvelocity = 100\n'
    '[[map]]\nkey = "f3"\ntype = "pc"\nchannel = 0\nprogram = 2\n'
)


class Ev:
    def __init__(self, keysym: str) -> None:
        self.keysym = keysym


# ---------------------------------------------------------------------------
# Lista de mapeamentos
# ---------------------------------------------------------------------------


def test_lista_populada_na_abertura(app_factory):
    app_factory(TOML_3MAPS)
    rows = [t for t in list_widget_texts("CTkButton", "CTkLabel") if "→" in t]
    assert len(rows) == 3
    assert any(t.startswith("F1") for t in rows)
    assert any(t.startswith("F3") and "PC" in t for t in rows)


def test_adicionar_tecla_reusa_entrada_vazia(app_factory):
    ui = app_factory(TOML_1MAP)
    n0 = len(ui._cfg.mappings)

    ui._add_mapping()  # não há entrada vazia -> cria uma nova e captura
    assert len(ui._cfg.mappings) == n0 + 1
    assert ui._capturing == ("mapping", n0)
    assert ui._on_capture_keypress(Ev("q")) == "break"
    assert ui._cfg.mappings[-1].key == "q" and ui._capturing is None

    ui._add_mapping()  # agora também não há vazia -> cria outra
    assert len(ui._cfg.mappings) == n0 + 2
    assert ui._capturing == ("mapping", n0 + 1)

    ui._cancel_capture()  # deixa vazia; próximo add DEVE reutilizá-la
    ui._selected = None
    ui._rebuild_edit_panel()
    before = len(ui._cfg.mappings)
    ui._add_mapping()
    assert len(ui._cfg.mappings) == before          # nenhuma criada
    assert ui._capturing == ("mapping", before - 1)  # aponta p/ a vazia


def test_escape_cancela_captura_sem_alterar(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._selected = 0
    ui._rebuild_edit_panel()
    ui._start_capture_map_key()
    assert ui._on_capture_keypress(Ev("Escape")) == "break"
    assert ui._capturing is None
    assert ui._cfg.mappings[0].key == "f1"


# ---------------------------------------------------------------------------
# Colisões gatilho x teclas mapeadas
# ---------------------------------------------------------------------------


def test_gatilho_nao_pode_ser_tecla_mapeada(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._start_capture_toggle_key()
    assert ui._on_capture_keypress(Ev("f1")) == "break"
    assert ui._cfg.toggle_key == "scroll lock"
    assert ui._capturing is None


def test_mapeada_nao_pode_ser_o_gatilho(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._selected = 0
    ui._rebuild_edit_panel()
    ui._start_capture_map_key()
    assert ui._on_capture_keypress(Ev("scroll_lock")) == "break"
    assert ui._cfg.mappings[0].key == "f1"
    assert ui._capturing is None


def test_tecla_normal_continua_sendo_aceita(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._selected = 0
    ui._rebuild_edit_panel()
    ui._start_capture_map_key()
    assert ui._on_capture_keypress(Ev("q")) == "break"
    assert ui._cfg.mappings[0].key == "q"


# ---------------------------------------------------------------------------
# Import durante captura pendente
# ---------------------------------------------------------------------------


def test_import_cancela_captura_pendente(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._selected = 0
    ui._start_capture_map_key()
    assert ui._capturing is not None

    ui._import()  # diálogo stub retorna "" — mas a captura já foi cancelada
    assert ui._capturing is None

    ui._on_capture_keypress(Ev("z"))  # tecla solta depois: nada deve quebrar
    assert all(m.key != "z" for m in ui._cfg.mappings)


# ---------------------------------------------------------------------------
# Layout fixo
# ---------------------------------------------------------------------------


def test_invariantes_do_layout(app_factory):
    ui = app_factory(TOML_1MAP)
    assert any(c.args[0] == "1120x800" for c in ui.geometry.call_args_list)
    assert ui._list_frame.grid.call_args.kwargs["sticky"] == "nsew"
    assert ui._monitor.grid.call_args.kwargs["sticky"] == "nsew"


def test_monitor_limitado_a_50_linhas(app_factory):
    from unittest.mock import MagicMock

    ui = app_factory(TOML_1MAP)
    ui._monitor._mocks["index"] = lambda *a: "60.0"
    delete = ui._monitor._mocks.setdefault("delete", MagicMock())
    ui._trim_monitor()
    delete.assert_called_once_with("51.0", "end")


# ---------------------------------------------------------------------------
# Conversão keysym do Tk -> nome da lib keyboard
# ---------------------------------------------------------------------------


def test_tk_keysym_to_name():
    assert tk_keysym_to_name("Escape") == "esc"
    assert tk_keysym_to_name("scroll_lock") == "scroll lock"
    assert tk_keysym_to_name("kp_enter") == "enter"
    assert tk_keysym_to_name("F1") == "f1"
    assert tk_keysym_to_name("abnt_c1") == "abnt c1"  # fallback: underscore->espaço


# ---------------------------------------------------------------------------
# UX P0: exclusão confirmada, FocusOut na captura, título refletindo estado
# ---------------------------------------------------------------------------

TOML_EMPTY = '[midi]\nport = ""\n[capture]\ntoggle_key = "scroll lock"\n'


def test_estado_vazio_da_lista(app_factory):
    app_factory(TOML_EMPTY)
    assert any("Nenhuma tecla mapeada" in t for t in list_widget_texts("CTkLabel"))


def test_delete_exige_segundo_clique(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._remove_mapping(0)
    assert len(ui._cfg.mappings) == 1                      # 1º clique só confirma
    cfg_btn = ui._delete_buttons[0]._mocks["configure"]
    assert cfg_btn.call_args.kwargs["text"] == "Certeza?"
    ui._remove_mapping(0)                                  # 2º clique apaga
    assert len(ui._cfg.mappings) == 0
    assert any("Nenhuma tecla mapeada" in t
               for t in list_widget_texts("CTkLabel"))      # estado vazio aparece


def test_focusout_cancela_captura(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._selected = 0
    ui._rebuild_edit_panel()
    ui._start_capture_map_key()
    assert ui._capturing is not None
    ui._on_focus_out()          # usuário clicou em outra janela
    assert ui._capturing is None


def test_titulo_reflete_interceptacao(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._engine._capture_active = True
    ui._reflect_state()
    assert "INTERCEPTANDO" in str(ui.title.call_args.args[0])

    ui._engine._capture_active = False
    ui._reflect_state()
    assert "INTERCEPTANDO" not in str(ui.title.call_args.args[0])
