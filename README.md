# MIDI-QWERTY

Mapeia **teclas do teclado QWERTY** para **comandos MIDI** e envia para sua DAW — feito para Windows, usando o [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) como ponte MIDI virtual.

Casos de uso típicos: ligar/desligar funções de plugins de guitarra (amp sim, bloqueador de ruído, looper), trocar presets via Program Change, acionar pedaleiras virtuais — sem tocar no mouse.

```
Teclado QWERTY ──► [hook global] ──► MIDI-QWERTY ──► loopMIDI ──► DAW / plugin
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

```powershell
# dentro da pasta do projeto (PowerShell)
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

> Se o PowerShell bloquear o `Activate.ps1` (*execution policy*), rode uma vez:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` — ou use o cmd clássico com `.venv\Scripts\activate.bat`.

Isso instala as dependências (`customtkinter`, `keyboard`, `mido`, `python-rtmidi`) e cria o comando `midi-qwerty`.

### loopMIDI

1. Instale e abra o loopMIDI.
2. Crie uma porta virtual clicando em **+** (nome padrão: `loopMIDI Port`).
3. Na DAW, habilite `loopMIDI Port` como **entrada MIDI** nos canais/trilhas desejados:
   - **Reaper**: `Options → Preferences → MIDI Devices → loopMIDI Port → Enable/Input`.
   - **Cakewalk Sonar**: veja a seção [Integrando com a DAW](#integrando-com-a-daw) — o roteamento para plugins FX é diferente.
   - No plugin, associe o parâmetro ao CC correspondente (*learn / MIDI learn*).

> O nome da porta criada no loopMIDI precisa ser o mesmo selecionado no app (seção abaixo).

---

## Integrando com a DAW

O princípio é sempre o mesmo: o app envia para a porta do loopMIDI e a DAW precisa receber essa porta e entregá-la ao plugin. Em DAWs como Reaper isso é direto (entrada MIDI na própria trilha que hospeda o FX). No **Cakewalk Sonar**, plugins de FX em trilha de áudio **não** recebem o MIDI da própria trilha — é preciso uma trilha MIDI "ponte":

### Cakewalk Sonar

```
MIDI-QWERTY ──► loopMIDI ──► TRILHA MIDI ──Output──► instância do plugin
                 (porta       in: loopMIDI Port     (FX instalado numa
                  virtual)                           trilha de áudio)
```

1. Trilha de áudio normal da guitarra com o amp sim como FX (monitoramento como de costume).
2. Abra a janela do plugin e habilite a entrada MIDI **interna** dele:
   - **Archetype (Neural DSP)**: ícone de MIDI no cabeçalho → ativar a entrada.
   - **Helix Stadium**: menu → MIDI. Atenção: **bypass/controle usa o canal 2 por padrão** (global/preset/snapshot é canal 1; snapshot = CC69).
3. Com a janela do plugin **em foco**, clique no botão **VST3** na barra do Sonar → **Enable MIDI Input**. Sem isso o plugin não aparece como destino de saída no passo seguinte.
4. `Insert → MIDI Track` (a ponte):
   - **Input**: `loopMIDI Port`
   - **Output**: a instância do plugin (ex.: `Archetype: X 1`, `Helix Stadium Native`)
   - **Input Echo**: **ligado** — sem eco, o MIDI ao vivo não passa enquanto o transporte está parado.
5. Modo captura **ATIVO** no app → entre no modo learn do plugin → aperte a tecla mapeada.

Quando estiver funcionando, salve como **Track Template** (`botão direito na trilha → Save as Track Template`) para reutilizar nos próximos projetos.

| Sintoma | Verificar |
|---|---|
| Plugin não aparece no Output da trilha MIDI | Passo 3 (`Enable MIDI Input`) |
| Aparece, mas nada chega | Input Echo desligado; input errado; porta desabilitada em Preferências → MIDI → Devices |
| Chega, mas o plugin ignora | Canal errado — no Helix, bypass/controle é canal 2 (mude o canal no mapa do app ou o canal do plugin para 1) |

---

## Uso

```powershell
midi-qwerty                 # usa .\config.toml
midi-qwerty --config C:\caminho\outro-mapa.toml
```

### Janela principal

1. **Saída MIDI** — selecione a porta do loopMIDI no dropdown. `↻ Atualizar` reescaneia as portas (útil se você criar a porta depois de abrir o app). A troca é aplicada na hora, sem reiniciar. O indicador à direita mostra `● conectado` quando a porta está aberta.
2. **Teclas mapeadas** — lista com resumo de cada mapeamento (`F1 → CC#20 toggle ch1`). Clique para editar; `✕` remove; `+ Adicionar tecla` cria um novo mapeamento e **já entra em modo de captura** — basta apertar a tecla desejada (se já existir uma entrada sem tecla, ela é reutilizada).
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
| Hooks não funcionam com a DAW aberta | Se a DAW estiver rodando **como administrador**, rode o `midi-qwerty` como administrador também. |
| Sonar: `undefined external error` ao habilitar entrada MIDI em Preferências → MIDI → Devices | Bug antigo do Windows (filtro `ksthunk` ausente na classe MEDIA do registro). Antes de mexer no registro, feche apps que seguram a porta (MIDI-QWERTY, standalone do plugin) e reabra o Sonar. Se persistir: `regedit` → chave `HKLM\SYSTEM\CurrentControlSet\Control\Class\{4D36E96C-E325-11CE-BFC1-08002BE10318}` (confira `(Default)` = *Sound, video and game controllers*) → crie um **Multi-String Value** chamado `UpperFilters` com valor `ksthunk` (case-sensitive; se já existir vazio, complete) → reinicie o Windows. Persistindo ainda: remova dispositivos MIDI "fantasmas" duplicados (Gerenciador de Dispositivos → Mostrar dispositivos ocultos). |
| Antivírus reclama dos hooks | Hooks globais de teclado podem gerar alerta; libere o executável/script. |

---

## Para desenvolvedores

```
src/midi_qwerty/
├── __main__.py   entry point CLI (--config, --version)
├── config.py     modelo de dados + TOML (carga/salva atômica, validação)
├── messages.py   MsgDesc (mensagem MIDI abstrata) + formatação p/ monitor
├── mapper.py     estado por tecla (held/toggle) + anti auto-repeat
├── midi.py       porta MIDI-out (mido/rtmidi) e conversão MsgDesc→mido
├── engine.py     thread própria: hooks, modo captura, fila de comandos/eventos
└── app.py        GUI CustomTkinter (auto-salva + aplica ao vivo)
tests/test_logic.py   cobertura da lógica pura (config, mapper, mensagens)
run.py                launcher p/ PyInstaller (imports absolutos)
```

Decisões de arquitetura:

- **Engine desacoplada da GUI**: toda mutação passa por uma fila de comandos processada por um único worker — evita mexer nos hooks dentro da thread de hook do `keyboard`.
- **`MsgDesc` independente de biblioteca**: mapper é 100% testável sem porta MIDI.
- **Salvamento atômico**: escreve em `.tmp` + `os.replace` — nunca corrompe a config.

Testes:

```bash
python -m pytest tests/ -q
```

Roadmap: perfis múltiplos com hot-swap; investigar a fundo o `undefined external error` do Sonar (workaround já documentado em Solução de problemas, falta a causa raiz nesta máquina).

---

## Versão executável/portável

**Status: implementada e validada em uso real** — `dist\MIDI-QWERTY.exe` funcionando com hooks, porta MIDI, auto-save e exportar/importar.

O exe é gerado via PyInstaller; os arquivos de build estão versionados (`run.py`, `MIDI_QWERTY.spec`, `build_exe.bat`). O build roda no Windows (PyInstaller não faz cross-build a partir do WSL/Linux) — para regenerar após mudanças no código:

```powershell
cd caminho\do\projeto
.\.venv\Scripts\Activate.ps1
pip install -e . pyinstaller
.\build_exe.bat          # gera dist\MIDI-QWERTY.exe
```

**Como funciona**

| Item | Decisão |
|---|---|
| Formato | `onefile` + `windowed` (exe único, sem console), nome `MIDI-QWERTY.exe` |
| Config no modo congelado | `config.toml` é criado/lido na **pasta do `.exe`** (detecção `sys.frozen` em `__main__.py`) — portátil de verdade: a pasta inteira pode ir para pendrive |
| Assets do CustomTkinter | `collect_data_files("customtkinter")` no spec (temas não são autodetectados) |
| Backend MIDI | `mido.backends.rtmidi` + `rtmidi` nos `hiddenimports` (carregado por string em `midi.py`) |
| UPX | desligado — reduz falso positivo de antivírus |

**Riscos conhecidos**
- Antivírus/SmartScreen podem acusar falso positivo com PyInstaller (comum); opções: assinar o binário ou distribuir o zip com instrução de liberação.
- A lib `keyboard` às vezes exige execução como admin se a DAW estiver elevada — vale um aviso no primeiro boot do exe.

**Checklist pós-build**
1. Hook global de teclado funciona sem console
2. Porta MIDI aparece no dropdown e mensagens chegam na DAW
3. Auto-save do config ao lado do exe; exportar/importar funcionam
4. Se SmartScreen reclamar: "Mais informações → Executar assim mesmo" ou liberar no Defender

---

## Licença

MIT.
