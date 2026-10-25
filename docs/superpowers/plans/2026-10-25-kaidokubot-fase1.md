# KaiDokuBot — Fase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bot de Telegram que recebe `nome preço [estado]` e responde em < 1 s com o que percebeu, as contas ¥→€ com o reembolso do tax-free e o botão «✏️ Corrigir»; câmbio automático com `/cambio`.

**Architecture:** Lógica pura (`parsing`, `rules`, `formatting`) testada por TDD; `storage` (SQLite) e `fx` (HTTP injetado) testados com fakes; `commands.py` concentra o comportamento do bot sem depender do Telegram (devolve `Resposta` com texto e botões); `telegram_bot.py` é uma camada fina. Mesmos padrões do VintedBot.

**Tech Stack:** Python 3.12 (PC) / 3.13 (Pi), `python-telegram-bot[job-queue]>=21.0,<23`, `python-dotenv>=1.0`, `httpx>=0.27`, `pytest>=8.0`, `pytest-asyncio>=0.23`.

**Spec:** `docs/superpowers/specs/2026-10-25-kaidokubot-design.md` (secções 1–4).

## Global Constraints
- Pacote `kaidokubot`; mensagens, comentários e docs em pt-PT; `from __future__ import annotations` em cada módulo, como no VintedBot.
- Testes nunca usam rede, Telegram nem Claude a sério.
- `pyproject.toml`: `asyncio_mode = "auto"`, `pythonpath = ["."]`, `testpaths = ["tests"]`.
- Correr os testes com `.venv/Scripts/python.exe -m pytest -q` (Windows).
- Commits em `main` sem `Co-Authored-By` nem outra atribuição ao Claude.
- Formato das contas, exato: `¥4.800 → €27.35 em loja · €24.86 após reembolso (+€2.49)`.
- Nota do mínimo, exata: `ℹ️ reembolso só se somares ≥ ¥5.500 nesta loja hoje`.

## Review Focus
1. Dígitos e símbolos de largura total do teclado japonês (`４８００円`, `￥4,800`) → normalizar com NFKC antes de tudo; teste em `test_parsing.py`.
2. Número no nome (`nendoroid 2367 frieren 4800`) → o último número é o preço e `2367` fica no nome; com `¥`/`円` noutro número, esse ganha; teste em `test_parsing.py`.
3. Primeiro arranque sem rede (nunca houve câmbio) → resposta mostra só ienes com "câmbio indisponível", nunca rebenta; teste em `test_formatting.py` e `test_fx.py`.
4. À espera de uma correção de preço e chega texto sem número → a espera é cancelada e o texto é tratado como pedido novo; teste em `test_commands.py`.
5. Botão de um pedido que não existe (id inválido ou BD apagada) → "Já não tenho esse pedido", sem exceção; teste em `test_commands.py`.

---

### Task 1: Esqueleto e config

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `.gitignore`, `.env.example`, `kaidokubot/__init__.py`, `kaidokubot/config.py`, `tests/__init__.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `ConfigError(Exception)`; `Settings(telegram_token: str, allowed_chat_id: int | None, db_path: str, claude_bin: str | None, claude_model: str, max_avaliacoes_dia: int, margem_minima: int, cache_dias: int)` (frozen dataclass); `load_settings(env: Mapping[str, str] | None = None, which=shutil.which) -> Settings`.

- [ ] **Step 1:** `.gitignore` e `requirements.txt` como no VintedBot (sem `curl_cffi`, com `httpx>=0.27`); `.env.example` comentado com `TELEGRAM_TOKEN`, `ALLOWED_CHAT_ID`, `CLAUDE_BIN`, `CLAUDE_MODEL=sonnet`, `MAX_AVALIACOES_DIA=30`, `MARGEM_MINIMA=20`, `CACHE_DIAS=30`, `DB_PATH=kaidokubot.db`. Criar `.venv` e instalar.
- [ ] **Step 2: Testes que falham** (`tests/test_config.py`)
```python
def test_defaults():
    s = load_settings({"TELEGRAM_TOKEN": "t"}, which=lambda _: None)
    assert (s.allowed_chat_id, s.db_path, s.claude_bin, s.claude_model) == (None, "kaidokubot.db", None, "sonnet")
    assert (s.max_avaliacoes_dia, s.margem_minima, s.cache_dias) == (30, 20, 30)

def test_values_are_parsed():  # ALLOWED_CHAT_ID=-100123, MARGEM_MINIMA=25, CLAUDE_BIN=/x/claude -> valores lidos

def test_claude_found_on_path():  # which=lambda n: f"/usr/bin/{n}" -> claude_bin == "/usr/bin/claude"

@pytest.mark.parametrize("env", [{}, {"TELEGRAM_TOKEN": ""}, {"TELEGRAM_TOKEN": "t", "ALLOWED_CHAT_ID": "abc"},
    {"TELEGRAM_TOKEN": "t", "MARGEM_MINIMA": "120"}, {"TELEGRAM_TOKEN": "t", "MAX_AVALIACOES_DIA": "-1"}])
def test_invalid_config_raises(env): ...
```
- [ ] **Step 3:** Correr `pytest tests/test_config.py -q` → FAIL (módulo não existe).
- [ ] **Step 4:** Implementar `config.py` ao estilo do VintedBot (`_int` com `ConfigError`); `MARGEM_MINIMA` em 0–90, `MAX_AVALIACOES_DIA` ≥ 0, `CACHE_DIAS` ≥ 1.
- [ ] **Step 5:** Testes passam; commit `feat: esqueleto do projeto e configuração`.

### Task 2: Parsing do texto

**Files:** Create `kaidokubot/parsing.py`, `tests/test_parsing.py`

**Interfaces:**
- Produces: `ESTADOS: tuple[str, ...] = ("selado", "novo", "usado", "sem caixa", "caixa danificada", "desconhecido")`; `Pedido(nome: str, preco_yen: int, estado: str)` (frozen dataclass); `ParseError(Exception)` (mensagem pt-PT para o utilizador); `parse_preco(texto: str) -> int | None`; `parse_estado(texto: str) -> str`; `parse_pedido(texto: str) -> Pedido`.

- [ ] **Step 1: Testes que falham**
```python
@pytest.mark.parametrize("texto, esperado", [
    ("nendoroid frieren 4800", Pedido("nendoroid frieren", 4800, "desconhecido")),
    ("zelda totk ¥3,980 sem caixa", Pedido("zelda totk", 3980, "sem caixa")),
    ("4.800円 pop up parade fern selado", Pedido("pop up parade fern", 4800, "selado")),
    ("nendoroid 2367 frieren 4800", Pedido("nendoroid 2367 frieren", 4800, "desconhecido")),
    ("¥4800 nendoroid 2367", Pedido("nendoroid 2367", 4800, "desconhecido")),
    ("ps5 slim 39800 yen usado", Pedido("ps5 slim", 39800, "usado")),
    ("figura ４８００円 未開封", Pedido("figura", 4800, "selado")),
    ("figura ￥4,800 箱傷み 中古", Pedido("figura", 4800, "caixa danificada")),
    ("Peluche Chiikawa 1.200 NOVO", Pedido("Peluche Chiikawa", 1200, "novo")),
])
def test_parse_pedido(texto, esperado): ...

@pytest.mark.parametrize("texto, estado", [("新品未開封", "selado"), ("開封品", "usado"), ("usado sem caixa", "sem caixa"),
    ("novo selado", "selado"), ("damaged box", "caixa danificada"), ("loose", "sem caixa"), ("Usada", "usado"), ("", "desconhecido")])
def test_parse_estado(texto, estado): ...

def test_sem_preco_da_erro():  # "nendoroid frieren" -> ParseError com "preço" na mensagem
def test_sem_nome_da_erro():   # "4800 selado" -> ParseError com "nome" na mensagem
def test_preco_fora_de_limites():  # "figura 0" e "figura 99999999" -> ParseError
def test_parse_preco_isolado():  # parse_preco("¥3.980") == 3980; parse_preco("sem número") is None
```
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3:** Implementar. NFKC primeiro. Regex de número: `\d{1,3}(?:[.,]\d{3})+|\d+`, com marcador opcional antes (`¥`) ou depois (`円`, `yen`, `jpy`, com espaço opcional). Palavras de estado da tabela do spec, por ordem de comprimento decrescente, comparadas sem acentos e sem maiúsculas; ganha a de maior prioridade (`caixa danificada` > `sem caixa` > `selado` > `usado` > `novo`). Para o nome, remover o token do preço (com o marcador) e as palavras de estado encontradas, conservando a capitalização original.
- [ ] **Step 4:** Testes passam; commit `feat: parsing de nome, preço e estado`.

### Task 3: Regras de dinheiro e formatação das contas

**Files:** Create `kaidokubot/rules.py`, `kaidokubot/formatting.py`, `tests/test_rules.py`, `tests/test_formatting.py`

**Interfaces:**
- Consumes: `Pedido`.
- Produces (`rules.py`): `IMPOSTO = 0.10`, `MINIMO_SEM_IMPOSTO = 5000`, `COMISSAO_REEMBOLSO = 0.0` sob o comentário `# premissas — confirmar antes da viagem`; `Contas(montra_yen: int, liquido_yen: float, montra_eur: float | None, liquido_eur: float | None)` com propriedade `reembolso_eur -> float | None`; `contas(montra_yen: int, taxa: float | None) -> Contas`; `abaixo_do_minimo(montra_yen: int) -> bool`.
- Produces (`formatting.py`): `fmt_yen(v: float) -> str` (`"¥4.800"`, arredonda às unidades); `fmt_eur(v: float) -> str` (`"€27.35"`); `linha_contas(c: Contas) -> str`; `resposta_imediata(p: Pedido, c: Contas) -> str` (HTML escapado); `HELP: str`.

- [ ] **Step 1: Testes que falham**
```python
TAXA = 0.0056979
def test_contas():
    c = contas(4800, TAXA)
    assert round(c.liquido_yen, 2) == 4363.64 and round(c.montra_eur, 2) == 27.35 and round(c.liquido_eur, 2) == 24.86
def test_contas_sem_taxa():  # contas(4800, None).montra_eur is None
def test_abaixo_do_minimo():  # 5499 -> True, 5500 -> False

def test_linha_contas():
    assert linha_contas(contas(4800, TAXA)) == "¥4.800 → €27.35 em loja · €24.86 após reembolso (+€2.49)"
def test_linha_contas_sem_cambio():
    assert linha_contas(contas(4800, None)) == "¥4.800 → €? (câmbio indisponível)"
def test_fmt_yen_milhares():  # fmt_yen(1234567) == "¥1.234.567"
def test_resposta_imediata():
    texto = resposta_imediata(Pedido("Nendoroid <Frieren>", 4800, "caixa danificada"), contas(4800, TAXA))
    assert texto.splitlines() == ["📦 <b>Nendoroid &lt;Frieren&gt;</b>",
        "¥4.800 → €27.35 em loja · €24.86 após reembolso (+€2.49)", "Estado: caixa danificada",
        "ℹ️ reembolso só se somares ≥ ¥5.500 nesta loja hoje"]
def test_resposta_imediata_sem_nota_acima_do_minimo():  # preço 6000 -> sem linha ℹ️
```
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3:** Implementar. `liquido_yen = montra / (1 + IMPOSTO) * (1 - COMISSAO_REEMBOLSO)`; `abaixo_do_minimo` usa `montra / (1 + IMPOSTO) < MINIMO_SEM_IMPOSTO`. `reembolso_eur = montra_eur - liquido_eur`. `HELP` explica os formatos (`nendoroid frieren 4800`, `zelda totk ¥3,980 sem caixa`), os estados e `/cambio`, `/id`.
- [ ] **Step 4:** Testes passam; commit `feat: contas do tax-free e resposta imediata`.

### Task 4: Storage

**Files:** Create `kaidokubot/storage.py`, `tests/test_storage.py`

**Interfaces:**
- Consumes: `Pedido`.
- Produces: `Storage(path: str = ":memory:")` com `add_pedido(chat_id: int, pedido: Pedido, now: float | None = None) -> int`, `get_pedido(pedido_id: int) -> Pedido | None`, `update_pedido(pedido_id: int, pedido: Pedido) -> None`, `get_kv(key: str) -> str | None`, `set_kv(key: str, value: str | None) -> None` (`None` apaga), `close()`.

- [ ] **Step 1: Testes que falham:** `test_pedido_ida_e_volta`, `test_update_pedido`, `test_pedido_inexistente_e_none`, `test_kv_set_get_apagar`, `test_persistencia_em_ficheiro` (escrever com uma `Storage(tmp_path/"x.db")`, fechar, reabrir e ler).
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3:** Implementar com `sqlite3`, `row_factory = sqlite3.Row`, tabelas `pedidos(id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id, nome, preco_yen, estado, criado_em REAL)` e `kv(key TEXT PRIMARY KEY, value TEXT)`, como no VintedBot.
- [ ] **Step 4:** Testes passam; commit `feat: storage SQLite para pedidos e valores`.

### Task 5: Câmbio

**Files:** Create `kaidokubot/fx.py`, `tests/fakes.py`, `tests/test_fx.py`

**Interfaces:**
- Consumes: `Storage.get_kv/set_kv`.
- Produces: `URL_BCE = "https://api.frankfurter.dev/v1/latest?base=JPY&symbols=EUR"`, `URL_ALTERNATIVA = "https://open.er-api.com/v6/latest/JPY"`; `EstadoCambio(taxa: float | None, data: str | None, fonte: str | None, manual: bool)`; `parse_taxa(texto: str) -> float | None` (aceita `0,0058`; só 0 < x < 1); `class Cambio(storage, http, now=time.time)` com `estado() -> EstadoCambio`, `taxa() -> float | None`, `async atualizar(force: bool = False) -> EstadoCambio`, `definir_manual(taxa: float) -> None`, `async voltar_auto() -> EstadoCambio`; `class HttpJson` (`async get_json(url) -> dict`, `httpx.AsyncClient(timeout=10)`, `close()`).
- Produces (`tests/fakes.py`): `FakeHttp(respostas: dict[str, dict | Exception])` com `.chamadas: list[str]`.

- [ ] **Step 1: Testes que falham**
```python
BCE = {"amount": 1.0, "base": "JPY", "date": "2026-10-23", "rates": {"EUR": 0.0057}}
ALT = {"result": "success", "time_last_update_utc": "Fri, 23 Oct 2026 00:02:31 +0000", "rates": {"EUR": 0.0058}}
async def test_atualiza_do_bce():  # taxa 0.0057, data "2026-10-23", fonte "BCE", manual False; guardado em kv
async def test_usa_alternativa_se_bce_falhar():  # FakeHttp({URL_BCE: RuntimeError(), URL_ALTERNATIVA: ALT}) -> 0.0058, fonte "open.er-api", data "2026-10-23"
async def test_sem_rede_mantem_ultimo_guardado():  # 1.ª atualização ok, 2.ª com force=True e ambos a falhar -> continua 0.0057
async def test_sem_rede_e_sem_historico():  # taxa() is None, não lança
async def test_nao_repete_no_mesmo_dia():  # now avança 1 h -> atualizar() não chama o HTTP outra vez; avança 20 h -> chama
async def test_manual_tem_prioridade_e_nao_e_substituido():  # definir_manual(0.006); atualizar(force=True) -> taxa 0.006, manual True
async def test_voltar_auto_atualiza_ja():  # voltar_auto() chama o BCE e manual False
@pytest.mark.parametrize("texto, v", [("0.0058", 0.0058), ("0,0058", 0.0058), ("abc", None), ("0", None), ("2", None)])
def test_parse_taxa(texto, v): ...
```
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3:** Implementar. Chaves kv: `fx_taxa`, `fx_data`, `fx_fonte`, `fx_atualizado_em`, `fx_manual`. Data da alternativa: converter `time_last_update_utc` para `AAAA-MM-DD`. Falhas de HTTP ou JSON inválido → `log.warning` e tentar a fonte seguinte.
- [ ] **Step 4:** Testes passam; commit `feat: câmbio automático BCE com alternativa e valor manual`.

### Task 6: Comandos e fluxo «Corrigir»

**Files:** Create `kaidokubot/commands.py`, `tests/test_commands.py`; Modify `kaidokubot/formatting.py` (texto do `/cambio`)

**Interfaces:**
- Consumes: `parse_pedido`, `parse_preco`, `ParseError`, `ESTADOS`, `contas`, `resposta_imediata`, `Storage`, `Cambio`, `parse_taxa`, `EstadoCambio`.
- Produces: `Resposta(texto: str, botoes: list[list[tuple[str, str]]] = [])` (rótulo, callback_data); `formatting.texto_cambio(e: EstadoCambio) -> str`; `class Commands(storage, cambio)` com:
  - `texto(chat_id: int, texto: str) -> Resposta`
  - `menu_corrigir(pedido_id: int) -> Resposta` (callback `fix:<id>`)
  - `pedir_campo(chat_id: int, pedido_id: int, campo: str) -> Resposta` (callback `fixf:<id>:nome|preco|estado`)
  - `definir_estado(pedido_id: int, indice: int) -> Resposta` (callback `st:<id>:<índice em ESTADOS>`)
  - `cancelar(chat_id: int) -> Resposta` (callback `fixx`)
  - `async cambio(args: list[str]) -> str`
- Botões da resposta imediata: `[[("✏️ Corrigir", f"fix:{id}")]]` (o «💡 Avaliar» entra na fase 2).

- [ ] **Step 1: Testes que falham** (`Storage()` em memória, `Cambio` com `FakeHttp` e taxa `0.0056979` já definida como manual)
```python
def test_texto_valido_guarda_pedido_e_responde():  # Resposta com a resposta_imediata e botão ("✏️ Corrigir", "fix:1")
def test_texto_invalido_explica():  # "nendoroid frieren" -> texto contém "preço", sem botões
def test_corrigir_preco():  # pedir_campo(..., "preco") pede o preço; texto("¥5,200") -> pedido 1 tem preço 5200 e a resposta refeita mostra ¥5.200
def test_corrigir_nome():  # pedir_campo(..., "nome"); texto("Nendoroid Fern") -> nome "Nendoroid Fern", preço inalterado
def test_corrigir_estado():  # pedir_campo(..., "estado") devolve 6 botões st:1:0..st:1:5; definir_estado(1, 0) -> estado "selado"
def test_preco_sem_numero_cancela_e_trata_como_novo():  # à espera de preço; texto("zelda 3980") -> pedido novo #2 (não altera o #1)
def test_pedido_inexistente():  # menu_corrigir(99) e definir_estado(99, 0) -> "Já não tenho esse pedido…"
def test_cancelar():  # à espera de nome; cancelar(); texto("abc 100") -> pedido novo
async def test_cambio_mostrar_manual_e_auto():  # cambio([]) mostra a taxa e "manual"; cambio(["0,006"]) fixa; cambio(["auto"]) volta ao BCE; cambio(["x"]) -> uso
```
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3:** Implementar. O estado "à espera de" fica em memória num `dict[chat_id, (pedido_id, campo)]`. À espera de preço: se `parse_preco` encontra um número e o texto, sem o preço, fica vazio, aplica; senão cancela e trata como pedido novo. À espera de nome: o texto todo é o nome. Depois de uma correção, a resposta é a `resposta_imediata` do pedido atualizado com os mesmos botões. `texto_cambio`: `💱 1 ¥ = €0.0057 (BCE, 2026-10-23)`, ou `(manual)`, ou `💱 Câmbio indisponível`, seguido de uma linha `¥1.000 = €5.70`.
- [ ] **Step 4:** Testes passam; commit `feat: comandos, /cambio e fluxo Corrigir`.

### Task 7: Telegram e arranque

**Files:** Create `kaidokubot/telegram_bot.py`, `kaidokubot/main.py`, `tests/test_telegram_bot.py`

**Interfaces:**
- Consumes: `Commands`, `Resposta`, `Cambio`, `HttpJson`, `Storage`, `Settings`, `HELP`.
- Produces: `markup(r: Resposta) -> InlineKeyboardMarkup | None`; `build_application(settings: Settings, storage: Storage, cambio: Cambio) -> Application`; `main()`.

- [ ] **Step 1: Testes que falham:** `test_markup_converte_botoes` (2 linhas, `callback_data` certos) e `test_markup_sem_botoes_e_none`.
- [ ] **Step 2:** Correr → FAIL.
- [ ] **Step 3:** Implementar ao estilo do VintedBot.
  - Filtros e handlers:
    - `filters.Chat(allowed)` em tudo menos `/id`; log de aviso se `ALLOWED_CHAT_ID` estiver vazio;
    - `/start` e `/help` → `HELP`;
    - `/cambio`;
    - `MessageHandler(filters.TEXT & ~filters.COMMAND & allowed)`;
    - `CallbackQueryHandler` para `^fix:\d+$`, `^fixf:\d+:(nome|preco|estado)$`, `^st:\d+:\d$`, `^fixx$`. O callback verifica o chat como no `on_price` do VintedBot.
  - Respostas: `ParseMode.HTML` e `disable_web_page_preview`.
  - Jobs do `job_queue`: `cambio.atualizar()` a cada 6 h (só chama a rede se tiverem passado 20 h ou mais) e 5 s depois do arranque.
  - `post_shutdown` fecha o `HttpJson` e o `Storage`.
  - `main.py` como no VintedBot: `WindowsSelectorEventLoopPolicy` no Windows e `ConfigError` → `sys.exit`.
- [ ] **Step 4:** `pytest -q` todo a passar; arranque manual com `.env` real no PC, `/id`, um pedido de texto, «Corrigir» preço e `/cambio`.
- [ ] **Step 5:** Commit `feat: bot de Telegram com resposta imediata`; `git push`.
