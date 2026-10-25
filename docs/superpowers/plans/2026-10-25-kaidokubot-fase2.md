# KaiDokuBot — Fase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** «💡 Avaliar» compara o custo na loja com a alternativa europeia mais barata (veredicto, preço máximo) e com o preço normal no Japão (Mercari), com progresso, fila, cache de 30 dias e limite diário; menus do «Corrigir» editados no lugar.

**Architecture:** `rules.py` ganha o custo de importar e o cálculo do veredicto (puro). `fontes.py` adapta Mercari (`mercapi`) e Vinted (cliente adaptado do VintedBot) para `Anuncio`. `claude.py` corre o `claude -p` em stream-json numa thread e devolve `structured_output`, avisando cada pesquisa web. `appraisal.py` orquestra: cache → limite → fila → termos → Mercari+Vinted → Claude → guarda. `telegram_bot.py` edita uma mensagem de progresso (no máximo a cada 3 s).

**Tech Stack:** + `mercapi>=0.5`, `curl_cffi>=0.7`, `tzdata` (Windows).

**Spec:** `docs/superpowers/specs/2026-10-25-kaidokubot-design.md` (secções 4–5).

## Global Constraints
- Igual à fase 1; **sem `git push`**.
- Testes nunca chamam Claude, Mercari, Vinted nem Telegram (fakes).
- Premissas novas em `rules.py`, no bloco "premissas — confirmar antes da viagem": `IVA_PT = 0.23`, `PORTES_IMPORTACAO_EUR = 15.0`, `TAXA_CTT_EUR = 2.65`.
- Dia do limite: meia-noite de `Asia/Tokyo`.

## Review Focus
1. Sem câmbio → veredicto ⚪ incerto com a razão "câmbio indisponível"; nunca rebenta (`test_rules.py`).
2. Mercari ou Vinted em baixo → a avaliação continua só com o que houver e diz o que falhou (`test_appraisal.py`).
3. Claude falha / timeout / JSON inválido → mensagem de erro curta e a avaliação **não** conta para o limite nem fica na cache (`test_appraisal.py`).
4. Duas avaliações ao mesmo tempo → a segunda vê "Na fila (posição 1)" e, se for o mesmo artigo, usa a cache que a primeira criou (`test_appraisal.py`).
5. Cache: mesmo nome com maiúsculas / acentos / espaços diferentes e mesmo estado → acerta; estado diferente → falha (`test_storage.py`).

---

### Task 1: Menus do «Corrigir» no lugar
- `Commands.cancelar(chat_id, pedido_id) -> Resposta` passa a devolver a resposta imediata; callback `fixx:<id>`.
- `Commands.botoes_pedido(pedido_id) -> list[list[tuple[str, str]]]` (os botões normais; na Task 7 ganha «💡 Avaliar»).
- Telegram: `fix`, `fixf:estado`, `st` e `fixx` editam a própria mensagem; `fixf:nome|preco` edita a mensagem para o pedido de texto ("✏️ Escreve o preço certo:" + Cancelar) e guarda o id dessa mensagem por chat; quando chega a correção, essa mensagem fica só com o texto do pedido (sem botões) e a resposta nova é enviada.
- Testes: `test_cancelar` atualizado; `test_menu_corrigir` com `fixx:1`.

### Task 2: Veredicto e custo de importar (puro)
- `rules.py`: `importar_total_eur(preco_yen: float, taxa: float) -> float`; `Mercado` (dataclass, ver Interfaces); `Veredicto(codigo: str, melhor: tuple[str, float] | None, poupanca_eur: float | None, poupanca_pct: float | None, max_montra_yen: int | None, caro_no_japao: bool, motivo: str | None)`; `calcular_veredicto(m: Mercado, c: Contas, taxa: float | None, margem_pct: int) -> Veredicto`. Códigos: `compensa` / `pouca` / `nao` / `incerto`.
- `Mercado` (JSON-serializável via `asdict`/`Mercado.from_dict`): `termo_jp, termo_en, novo_eu_eur, novo_eu_loja, vinted_min_eur, vinted_max_eur, vinted_n, importar_yen, importar_loja, jp_min_yen, jp_max_yen, jp_n, jp_so_pedidos, cenarios: list[dict], razao, fontes: list[dict], avisos: list[str]`.
- `formatting.resultado(p: Pedido, c: Contas, m: Mercado, v: Veredicto, criado_em: float | None, agora: float) -> str`.
- Testes com valores fixos: compensa (poupança ≥ 20%), pouca, não, incerto (sem alternativas / sem câmbio), max_montra arredondado à centena para baixo, caro_no_japao, importar_total; formatação completa com e sem cache ("🕒 avaliado há 4 dias").

### Task 3: Storage de avaliações, cache e contagem
- `chave_cache(nome: str, estado: str) -> str` (minúsculas, sem acentos, espaços normalizados, NFKC).
- `Storage.add_avaliacao(chat_id, pedido_id, pedido, mercado_json: str, veredicto: str, da_cache: bool, now=None) -> int`; `Storage.cache(chave: str, desde: float) -> tuple[str, float] | None` (json do mercado mais recente não-cache, criado_em); `Storage.contar_avaliacoes(desde: float) -> int` (só `da_cache = 0`).
- `appraisal.inicio_do_dia_tokyo(agora: float) -> float`.

### Task 4: Fontes (Mercari, Vinted)
- `fontes.py`: `Anuncio(titulo: str, preco: float, estado: str)`; `FonteError`; `class Mercari` com `async procurar(termo: str, n: int = 40) -> tuple[list[Anuncio], list[Anuncio]]` (vendidos, à venda; estado a partir de `item_condition_id`: 1 novo/未使用, 2 quase novo, 3 sem marcas, 4 marcas ligeiras, 5 marcas, 6 mau estado); `class Vinted` com `async procurar(termo: str) -> list[Anuncio]` (preço = `total_item_price` ou `price`; estado = última parte de `item_box.second_line` depois de "·").
- Testes da conversão com dicionários/objetos falsos; smoke real manual.

### Task 5: Claude CLI em stream-json
- `claude.py`: `ClaudeError(Exception)`; `ler_stream(linhas: Iterable[str], on_search: Callable[[str], None] | None) -> dict` (puro: chama `on_search(query)` para cada `tool_use` WebSearch, devolve `structured_output` do evento `result`; `is_error`/sem resultado → `ClaudeError`); `class ClaudeCli(binary, model, timeout_s=300)` com `async run(prompt: str, schema: dict, *, system: str, tools: str, on_search=None) -> dict` (Popen numa thread, `on_search` reencaminhado para o loop com `call_soon_threadsafe`, timeout mata o processo).
- Testes de `ler_stream` com linhas reais do teste da fase 0.

### Task 6: Avaliador
- `appraisal.py`: `class Avaliador(storage, cambio, runner, mercari, vinted, *, max_dia: int, margem: int, cache_dias: int, now=time.time)` com `async avaliar(chat_id: int, pedido_id: int, forcar: bool, progresso: Callable[[str], Awaitable[None]]) -> Resposta`.
- Ordem: pedido inexistente → `NAO_EXISTE`; cache (se não `forcar`) → resultado com "🕒" e botão «🔄 Reavaliar» (`rv:<id>`), conta como `da_cache`; limite → "Atingiste o limite de N avaliações hoje…"; fila (posição) → lock → cache outra vez → termos (Claude sem ferramentas) → Mercari e Vinted em paralelo → Claude com WebSearch → guarda → resultado com «🔄 Reavaliar» e «✏️ Corrigir».
- Prompts e esquemas JSON aqui (`SCHEMA_TERMOS`, `SCHEMA_MERCADO`, `SYSTEM_PROMPT`, `prompt_mercado(...)`).
- Testes com `FakeRunner` (respostas por esquema, regista prompts, simula pesquisas), `FakeFonte`.

### Task 7: Telegram
- Botões do pedido: `[("💡 Avaliar", f"av:{id}"), ("✏️ Corrigir", f"fix:{id}")]` se o Claude estiver configurado e `MAX_AVALIACOES_DIA > 0`.
- Handler `^(av|rv):\d+$` com `block=False`: envia "🔎 A preparar…" como resposta à mensagem do pedido, edita-a com o progresso (máx. a cada 3 s, sempre a última), e no fim com o resultado.
- `main.py` cria `ClaudeCli`, `Mercari`, `Vinted` e fecha-os no shutdown.
- Teste real no PC.
