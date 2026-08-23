# midi_cc

Mapeia **teclas do teclado QWERTY** para **comandos MIDI** e envia para sua DAW — feito para Windows, usando o [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) como ponte MIDI virtual.

Casos de uso típicos: ligar/desligar funções de plugins de guitarra (amp sim, bloqueador de ruído, looper), trocar presets via Program Change, acionar pedaleiras virtuais — sem tocar no mouse.

```
Teclado QWERTY ──► [hook global] ──► midi_cc ──► loopMIDI ──► DAW / plugin
                    (engole as      (mapeia)     (porta       (entrada MIDI)
                     teclas)                      virtual)
```

---

## Requisitos

| Item | Observação |
|---|---|
| Windows 10/11 | os hooks globais de teclado são específicos do Windows |
| Python 3.11+ | usa `tomllib` da stdlib |
| [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) | cria a porta MIDI virtual que a DAW recebe |
| DAW com entrada MIDI configurada | ex.: Reaper, Ableton, etc. |

---

## Instalação

```bat
:: dentro da pasta do projeto
py -3 -m venv .venv
.venv\Scripts\activate
pip install -e .
```

Isso instala as dependências (`customtkinter`, `keyboard`, `mido`, `python-rtmidi`) e cria o comando `midi-cc`.

### loopMIDI

1. Instale e abra o loopMIDI.
2. Crie uma porta virtual clicando em **+** (nome padrão: `loopMIDI Port`).
3. Na DAW, habilite `loopMIDI Port` como **entrada MIDI** nos canais/trilhas desejados:
   - **Reaper**: `Options → Preferences → MIDI Devices → loopMIDI Port → Enable/Input`.
   - No plugin, associe o parâmetro ao CC correspondente (*learn / MIDI learn*).

> O nome da porta criada no loopMIDI precisa ser o mesmo selecionado no app (seção abaixo).

---

## Uso

```bat
midi-cc                 :: usa .\config.toml
midi-cc --config C:\caminho\outro-mapa.toml
```

### Janela principal

1. **Saída MIDI** — selecione a porta do loopMIDI no dropdown. `↻ Atualizar` reescaneia as portas (útil se você criar a porta depois de abrir o app). A troca é aplicada na hora, sem reiniciar. O indicador à direita mostra `● conectado` quando a porta está aberta.
2. **Teclas mapeadas** — lista com resumo de cada mapeamento (`F1 → CC#20 toggle ch1`). Clique para editar; `✕` remove; `+ Adicionar tecla` cria um novo mapeamento.
3. **Painel de edição** (aparece ao selecionar uma tecla):
   - **🎹 Capturar** — clique e aperte a tecla física que quer usar (Esc cancela). Não precisa digitar nomes.
   - **Tipo de ação** e **Canal MIDI** (exibido como 1–16).
   - Campos dinâmicos conforme o tipo (ver tabela abaixo). Teclas duplicadas são bloqueadas.
4. **Tecla gatilho do modo captura** — por padrão `Scroll Lock`. Aperte-a em qualquer lugar do sistema para ligar/desligar o modo captura.
5. **Modo captura** — quando **ATIVO**, as teclas mapeadas são interceptadas e *engolidas* (não digitam nada na DAW). Quando INATIVO, o teclado volta ao normal.
6. **Monitor de mensagens** — mostra em tempo real cada mensagem enviada, ex.:

   ```
   [14:32:07] F1 → CC ch1 #20 = 127
   [14:32:09] F1 → CC ch1 #20 = 0
   [14:32:12] F2 → PC ch1 prog 3
   ```

   Mensagens com `⚠ sem porta` indicam que a saída MIDI não está aberta.

### Tipos de ação

| Tipo | Campos | Comportamento |
|---|---|---|
| **CC alternar (toggle)** | Nº CC, Valor ON, Valor OFF | Cada pressionada alterna entre ON/OFF. Ex.: ligar/desligar um efeito. |
| **CC momentâneo** | Nº CC, Valor ao pressionar, Valor ao soltar | Segura = valor alto; solta = volta. Ex.: pedal momentâneo. |
| **Nota (note on/off)** | Nota, Velocidade | Note On ao apertar, Note Off ao soltar. |
| **Program Change** | Nº do programa | Envia PC ao apertar. Ex.: trocar preset. |

Auto-repeat do Windows é ignorado: segurar uma tecla não dispara flood.

---

## Arquivos de configuração

- **Arquivo vivo**: `config.toml` (ou o caminho passado em `--config`). É **salvo automaticamente** a cada alteração na GUI e aplicado na engine imediatamente. Pode ser editado à mão também.
- **Exportar**: grava um snapshot do mapeamento atual num arquivo à sua escolha (preset, ex.: `mapa-plugin-x.toml`). Esse arquivo nunca mais é tocado pelo app.
- **Importar**: substitui o mapeamento atual pelo conteúdo do arquivo escolhido (com confirmação). O importado permanece intacto — só o arquivo atual/vivo é auto-salvo.

### Referência do TOML

```toml
[midi]
port = "loopMIDI Port"     # nome exato da porta no loopMIDI

[capture]
toggle_key = "scroll lock" # "" desativa a gatilho global (só pela GUI)

[[map]]                    # repita um bloco por tecla
key = "f1"                 # nome minúsculo da tecla
type = "cc_toggle"         # cc_toggle | cc_momentary | note | pc
channel = 0                # 0–15 (canal 1 = 0)
cc = 20                    # cc_toggle/cc_momentary
on_value = 127             # cc_toggle
off_value = 0              # cc_toggle
# press_value = 127        # cc_momentary
# release_value = 0        # cc_momentary
# note = 60                # note
# velocity = 100           # note
# program = 3              # pc
```

---

## Solução de problemas

| Sintoma | Causa provável / solução |
|---|---|
| Mensagens com `⚠ sem porta` no monitor | Porta não aberta: confira se o loopMIDI está rodando e se o nome bate; use `↻ Atualizar`. |
| A porta não aparece no dropdown | Crie a porta no loopMIDI e clique em `↻ Atualizar`. |
| Teclas mapeadas digitam letras na DAW | Modo captura está INATIVO — aperte a tecla gatilho (Scroll Lock) ou o botão na GUI. |
| Nada chega na DAW | Confira se a entrada MIDI `loopMIDI Port` está habilitada na trilha/plugin e se o nº de canal/CC coincide. Use o monitor para confirmar o que foi enviado. |
| Hooks não funcionam com a DAW aberta | Se a DAW estiver rodando **como administrador**, rode o `midi-cc` como administrador também. |
| Antivírus reclama dos hooks | Hooks globais de teclado podem gerar alerta; libere o executável/script. |

---

## Para desenvolvedores

```
src/midi_cc/
├── __main__.py   entry point CLI (--config, --version)
├── config.py     modelo de dados + TOML (carga/salva atômica, validação)
├── messages.py   MsgDesc (mensagem MIDI abstrata) + formatação p/ monitor
├── mapper.py     estado por tecla (held/toggle) + anti auto-repeat
├── midi.py       porta MIDI-out (mido/rtmidi) e conversão MsgDesc→mido
├── engine.py     thread própria: hooks, modo captura, fila de comandos/eventos
└── app.py        GUI CustomTkinter (auto-salva + aplica ao vivo)
tests/test_logic.py   cobertura da lógica pura (config, mapper, mensagens)
```

Decisões de arquitetura:

- **Engine desacoplada da GUI**: toda mutação passa por uma fila de comandos processada por um único worker — evita mexer nos hooks dentro da thread de hook do `keyboard`.
- **`MsgDesc` independente de biblioteca**: mapper é 100% testável sem porta MIDI.
- **Salvamento atômico**: escreve em `.tmp` + `os.replace` — nunca corrompe a config.

Testes:

```bash
python -m pytest tests/ -q
```

Roadmap: empacotamento com PyInstaller (exe único), perfis múltiplos com hot-swap.

---

## Licença

MIT.
