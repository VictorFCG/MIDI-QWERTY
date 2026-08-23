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

    # painel de edição na coluna da lista, em linha PRÓPRIA (não sobrepõe!)
    gp = ui._edit_panel.grid.call_args.kwargs
    gl = ui._list_frame.grid.call_args.kwargs
    assert (gp["row"], gp["column"]) == (2, 0) and gp["sticky"] == "ew"
    assert (gl["row"], gl["column"]) == (1, 0)

    # a linha flexível do corpo é a da LISTA (row 1) — nunca a dos cabeçalhos
    rc = {c.args[0]: c.kwargs.get("weight") for c in ui._body.grid_rowconfigure.call_args_list}
    assert rc.get(1) == 1 and rc.get(0, 0) in (None, 0)


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
    ui._mocks["focus_get"] = lambda: None       # foco foi p/ outra janela
    ui._on_focus_out()
    assert ui.after_idle.call_args.args[0] is not None
    ui.after_idle.call_args.args[0]()           # decide com foco assentado
    assert ui._capturing is None


def test_focusout_interno_mantem_captura(app_factory):
    """Cenário do bug: clicar '+ Adicionar' dispara FocusOut do botão
    clicado (transição interna) logo após o bind — não pode cancelar."""
    ui = app_factory(TOML_1MAP)
    ui._add_mapping()                            # já entra em captura
    assert ui._capturing is not None
    ui._mocks["focus_get"] = lambda: ui          # foco no próprio toplevel
    ui._on_focus_out()
    ui.after_idle.call_args.args[0]()
    assert ui._capturing is not None             # continua capturando


def test_tecla_solta_em_entry_nao_vira_binding(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._selected = 0
    ui._rebuild_edit_panel()
    ui._start_capture_map_key()

    ev = Ev("1")
    ev.widget = ".!ctkframe.!ctkentry"           # evento veio de um campo
    assert ui._on_capture_keypress(ev) == ""
    assert ui._cfg.mappings[0].key == "f1"       # nada atribuído

    ev2 = Ev("q")
    assert ui._on_capture_keypress(ev2) == "break"
    assert ui._cfg.mappings[0].key == "q"


def test_titulo_reflete_interceptacao(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._engine._capture_active = True
    ui._reflect_state()
    assert "INTERCEPTANDO" in str(ui.title.call_args.args[0])

    ui._engine._capture_active = False
    ui._reflect_state()
    assert "INTERCEPTANDO" not in str(ui.title.call_args.args[0])


# ---------------------------------------------------------------------------
# UX P1: navegação por teclado, clamp visível, tela pequena, hotkey falha
# ---------------------------------------------------------------------------


def test_painel_de_edicao_grid_sem_sobra_entre_os_pares(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._selected = 0
    ui._rebuild_edit_panel()

    # peso só na coluna espaçadora final — pares de campos ficam juntos
    wc = {c.args[0]: c.kwargs.get("weight")
          for c in ui._edit_panel.grid_columnconfigure.call_args_list}
    assert wc.get(4) == 1
    assert all((wc.get(i) or 0) == 0 for i in range(4))

    # rótulo do valor da tecla em célula própria (sem hack de padx sobre botão)
    gk = ui._lbl_map_key.grid.call_args.kwargs
    assert gk["column"] == 2 and gk["padx"] == (12, 6)


def test_seta_move_selecao_e_delete_marca(app_factory):
    ui = app_factory(TOML_3MAPS)
    assert ui._move_selection(1) == "break"
    assert ui._selected == 0                       # de None vai para a 1ª
    ui._move_selection(1)
    ui._move_selection(-5)                          # clampa no início
    assert ui._selected == 0

    ui._selected = 0
    ui._rebuild_edit_panel()
    ui._on_delete_key()                             # 1º Del: só confirma
    assert len(ui._cfg.mappings) == 3
    ui._on_delete_key()                             # 2º Del: apaga
    assert len(ui._cfg.mappings) == 2


def test_navegacao_ignora_entry_e_captura(app_factory):
    ui = app_factory(TOML_3MAPS)

    class FakeFocus:
        winfo_name = "ctkentry"                     # foco num campo de texto

    ui._mocks["focus_get"] = lambda: FakeFocus()
    ui._move_selection(1)
    assert ui._selected is None                     # não roubou o ↑/↓ do campo

    ui._mocks["focus_get"] = lambda: None
    ui._capturing = ("mapping", 0)                  # durante captura, ignora
    ui._move_selection(1)
    assert ui._selected is None
    ui._capturing = None


def test_clamp_avisa_o_usuario(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._selected = 0
    ui._rebuild_edit_panel()
    ui._menus["type"]._mocks["get"] = lambda: "CC alternar (toggle)"
    ui._menus["channel"]._mocks["get"] = lambda: "1"
    ui._entries["cc"]._mocks["get"] = lambda: "999"
    assert ui._read_panel_into() is True            # valor válido após clamp
    assert ui._cfg.mappings[0].action.cc == 127
    warn = ui._warn_lbl._mocks["configure"].call_args.kwargs["text"]
    assert "999 → 127" in warn


def test_janela_clampa_em_tela_pequena(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._mocks["winfo_screenwidth"] = lambda: 1366
    ui._mocks["winfo_screenheight"] = lambda: 768   # notebook comum
    assert ui._initial_geometry() == "1120x668"


def test_hotkey_falha_mostra_aviso_no_gatilho(app_factory):
    ui = app_factory(TOML_1MAP)
    ui._engine._toggle_hk_ok = False                # registro da hotkey falhou
    ui._reflect_state()
    hint = ui._lbl_trig_hint._mocks["configure"].call_args.kwargs["text"]
    assert "Capturar tecla" in hint

    ui._engine._toggle_hk_ok = True
    ui._reflect_state()
    hint_ok = ui._lbl_trig_hint._mocks["configure"].call_args.kwargs["text"]
    assert hint_ok == ""
