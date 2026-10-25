# KaiDokuBot — desenho

買い得 (kaidoku) = "boa compra". Bot de Telegram pessoal que, de pé numa loja no Japão, me diz se compensa comprar um artigo ali em vez de o comprar na Europa.

## Porquê e para quem
- Viagem ao Japão no fim de novembro de 2026 para comprar merch (figuras prize / Nendoroid / POP UP PARADE / scale, peluches, jogos, consolas), muitas vezes em lojas de usados (Mandarake, Suruga-ya, Book-Off, Lashinbang, Trader).
- Compro só para mim. O meu mercado é o europeu: a pergunta principal é **"compensa comprar aqui em vez de comprar na Europa?"**. A pergunta secundária é **"estou numa loja cara para o Japão? vale a pena ver noutra loja do itinerário?"**.
- Uso no telemóvel, de pé na loja: a resposta tem de ser rápida de pedir e ajudar a decidir na hora.
- Só um utilizador (`ALLOWED_CHAT_ID`); todas as outras contas são ignoradas (exceto `/id`).

## Objetivos
1. Resposta imediata (sem IA, < 1 s) com o que percebi e as contas ¥ → €.
2. Avaliação por IA (1–4 min) com veredicto face à Europa, preço máximo a pagar e o preço normal no Japão.
3. Funciona com texto e com foto da etiqueta.
4. Não gasta a subscrição Claude sem eu dar conta (cache, limite diário).

## Não-objetivos
- Dizer em que loja física do Japão há stock mais barato (Suruga-ya bloqueia acessos de Portugal, Mandarake é JavaScript): só dizemos o preço normal no Japão.
- Revenda, multiutilizador, interface web.
- Ligação à app "Can You Carry It" (os dados dela vivem só no iPhone).

## Anti-objetivos (falha mesmo que "funcione")
- Inventar números: sem dados fiáveis o veredicto é ⚪ incerto, com a razão.
- Respostas longas que obrigam a ler muito na loja.
- O bot ficar preso ou calado: há sempre uma mensagem de progresso ou de erro.

## Restrições
- Raspberry Pi 5, Python 3.13, `claude` CLI em `~/.local/bin/claude` com a minha subscrição, ao lado do VintedBot. Desenvolvimento no PC Windows (Python 3.12).
- Mesmos padrões do VintedBot (`C:\Users\Diogo\Documents\GitHub\VintedBot`): `run_claude` com `claude -p ... --json-schema`, `asyncio.to_thread` + `subprocess` (o event loop Selector do Windows não suporta subprocessos asyncio), `config.py` com `.env` e `ConfigError`, `python-telegram-bot[job-queue]`, `python-dotenv`, `pytest`, `pytest-asyncio`, script de arranque + serviço systemd e `deploy.sh`.
- Mensagens, comentários e docs em pt-PT.
- TDD na lógica pura; os testes nunca chamam o Claude, o Telegram nem a rede a sério (fakes).
- Commits diretos em `main`, sem `Co-Authored-By` nem outra atribuição ao Claude.

## Arquitetura (pacote `kaidokubot`)
| Módulo | Responsabilidade |
|---|---|
| `main.py` | arranque, logging, `ConfigError` → mensagem clara |
| `config.py` | `.env` → `Settings` |
| `parsing.py` | texto → `Pedido(nome, preco_yen, estado)` (puro) |
| `rules.py` | premissas de dinheiro e contas (puro) |
| `fx.py` | câmbio ¥→€ automático / manual (HTTP injetado) |
| `storage.py` | SQLite: pedidos, câmbio, cache, histórico, contagem diária |
| `formatting.py` | todas as mensagens HTML (puro) |
| `appraisal.py` | avaliação por IA: fila, cache, limite, pipeline, `PriceCheckError` (fase 2) |
| `mercari.py` | vendidos / à venda no Mercari (fase 2) |
| `vision.py` | foto → `Pedido` (fase 3) |
| `telegram_bot.py` | handlers, botões, fluxo «Corrigir» |

### Configuração (`.env`)
`TELEGRAM_TOKEN` (obrigatório), `ALLOWED_CHAT_ID`, `CLAUDE_BIN` (por omissão `which claude`), `CLAUDE_MODEL=sonnet`, `MAX_AVALIACOES_DIA=30`, `MARGEM_MINIMA=20` (%), `CACHE_DIAS=30`, `DB_PATH=kaidokubot.db`. O dia do limite diário vira à meia-noite de `Asia/Tokyo`.

## 1. Entrada por texto (`parsing.py`)
Exemplos: `nendoroid frieren 4800`, `zelda totk ¥3,980 sem caixa`, `4.800円 pop up parade fern selado`.

- **Preço:** o yen não tem decimais, por isso `.` e `,` entre dígitos são sempre separadores de milhares (`4.800` = `4,800` = 4800). Se algum número tiver `¥`, `￥`, `円`, `yen` ou `JPY` colado ou a seguir, é esse o preço; senão é o último número. Válido entre 1 e 10 000 000. Sem preço → peço-o.
- **Estado:** palavras-chave em pt-PT / inglês / japonês, sem distinguir maiúsculas e acentos. Estados: `selado`, `novo`, `usado`, `sem caixa`, `caixa danificada`, `desconhecido`. Com várias palavras, ganha a mais específica: `caixa danificada` > `sem caixa` > `selado` > `usado` > `novo`. A correspondência é pela expressão mais longa primeiro (`未開封` é selado, não "開封" = usado; `新品未開封` é selado).

  | Estado | Palavras-chave (exemplos) |
  |---|---|
  | selado | selado, sealed, misb, nib, 未開封, 新品未開封 |
  | novo | novo, nova, new, 新品, 未使用 |
  | usado | usado, usada, used, aberto, opened, 中古, 開封, 開封済み, 開封品 |
  | sem caixa | sem caixa, no box, loose, 箱なし, 箱無し, 本体のみ |
  | caixa danificada | caixa danificada, caixa estragada, damaged box, box damage, 箱傷み, 箱ダメージ, 箱潰れ |
- **Nome:** o texto sem o preço e sem as palavras de estado, com espaços normalizados. Vazio → peço o nome.

## 2. Regras de dinheiro (`rules.py`, comentário "premissas — confirmar antes da viagem")
- Desde 1/11/2026 o tax-free é por reembolso: pago o preço de montra (com 10%) e o imposto é devolvido após a verificação na alfândega à saída (até 90 dias). Assumo tudo reembolsável: `liquido = montra / 1.10`. `COMISSAO_REEMBOLSO = 0.0` (depende da loja; ex.: PPIH só cobra em dinheiro).
- Mínimo de ¥5.000 **sem imposto** por loja e por dia (somando as compras do dia na mesma loja; já não há separação entre gerais e consumíveis). Se `montra / 1.10 < 5000` (montra < ¥5.500) a resposta diz: *"reembolso só se somares ≥ ¥5.500 nesta loja hoje"*.
- Câmbio: `eur = yen × taxa`.
- Formato: `¥4.800 → €27.35 em loja · €24.86 após reembolso (+€2.49)` (yen com `.` de milhares; euros com 2 casas decimais).
- Fase 2: custo de importar do Japão = preço da loja online (sem imposto japonês) + portes + IVA 23% sobre (preço + portes) + taxa de desalfandegamento CTT (premissa, a confirmar).

## 3. Câmbio (`fx.py`)
- Automático: `https://api.frankfurter.dev/v1/latest?base=JPY&symbols=EUR` (BCE, sem chave); alternativa `https://open.er-api.com/v6/latest/JPY`. Atualizado 1× por dia (job do `job_queue` + no arranque se estiver desatualizado) e guardado no SQLite com a data e a fonte.
- Sem rede: usa o último guardado. Nunca houve câmbio: a resposta mostra só os ienes e "câmbio indisponível".
- `/cambio` mostra o valor, a data e se é automático ou manual; `/cambio 0.0058` fixa um valor manual (aceita `0,0058`); `/cambio auto` volta ao automático e atualiza já.
- HTTP com `httpx` (async), injetado para os testes.

## 4. Resposta imediata (sem IA)
```
📦 Nendoroid Frieren
¥4.800 → €27.35 em loja · €24.86 após reembolso (+€2.49)
Estado: caixa danificada
ℹ️ reembolso só se somares ≥ ¥5.500 nesta loja hoje
[💡 Avaliar] [✏️ Corrigir]
```
- Cada pedido é guardado no SQLite (`pedidos`) com um id, para os botões continuarem a funcionar depois de reiniciar.
- **«✏️ Corrigir»** → botões Nome / Preço / Estado / Cancelar. Nome e Preço: o bot pede o valor e a mensagem de texto seguinte substitui só esse campo. Estado: botões com os estados. Depois envia a resposta imediata refeita.
- «💡 Avaliar» só aparece a partir da fase 2 (e se o `claude` estiver configurado).

## 5. Avaliação por IA (fase 2)
Pipeline (uma única mensagem de progresso, editada no máximo a cada ~3 s):
1. **Fila:** um pedido de IA de cada vez (`asyncio.Lock` + contador); enquanto espera: "⏳ Na fila (posição 2)…".
2. **Limite diário:** `MAX_AVALIACOES_DIA` avaliações (contadas no SQLite, dia de Tóquio); acima disso recusa e diz quando volta. Respostas da cache não contam.
3. **Cache:** chave = nome normalizado (minúsculas, sem acentos, espaços normalizados) + estado; válida `CACHE_DIAS` (30) dias. O preço não entra na chave: os dados de mercado são reutilizados e o veredicto é recalculado para o preço atual. A resposta diz de quando é ("avaliado há 4 dias") e tem «🔄 Reavaliar».
4. **Termos japoneses:** chamada rápida ao Claude sem ferramentas → termo de pesquisa japonês (ex.: `ねんどろいど フリーレン`) e inglês. Com foto, sai do passo da visão.
5. **Mercari** (`mercapi`, API não oficial; testado a funcionar a partir de Portugal): até 40 vendidos e 40 à venda, com preço, estado e título. Progresso: "🔎 Mercari: 40 vendidos…". Se falhar, continua sem Mercari e diz isso.
6. **Claude com `WebSearch`** (stream-json; cada pesquisa aparece no progresso: "🌐 A pesquisar: …"). Recebe o pedido e a lista do Mercari (alguns não são comparáveis; ignora esses) e devolve, no `--json-schema`:
   - Europa: preço novo mais baixo em lojas europeias (€, loja); usado na Vinted / eBay (€ intervalo); custo de importar do Japão (preço da loja online, portes); `null` no que não encontrar;
   - Japão: intervalo dos vendidos comparáveis no Mercari para o mesmo estado (¥), e se só havia anúncios à venda;
   - com estado desconhecido: intervalos por cenário principal;
   - razão (≤ 3 frases, pt-PT) e 2–4 fontes `{nome, url}`.
   Prompt: termos japoneses e ingleses, preferir vendas concluídas a preços pedidos, ajustar ao estado, nunca inventar números.
7. **Veredicto calculado no código** (não pelo Claude), a partir da alternativa europeia mais barata no mesmo estado (`melhor_eu`) e do líquido em €:
   - poupança = `1 − liquido_eur / melhor_eu`;
   - 🟢 compensa: poupança ≥ `MARGEM_MINIMA`; 🟡 pouca diferença: 0 ≤ poupança < margem; 🔴 não compensa: poupança < 0; ⚪ incerto: sem `melhor_eu`;
   - "pagaria no máximo ¥X" = montra em que a poupança é exatamente a margem: `melhor_eu × (1 − margem) / taxa × 1.10`, arredondado para baixo à centena;
   - Japão: se a montra estiver acima do máximo dos vendidos comparáveis no Mercari → "👀 Acima do normal no Japão — vê noutras lojas".
8. Resultado (substitui a mensagem de progresso):
```
🟢 Compensa — poupas €20 (45%)
💴 Pagaria no máximo ¥6.900
🇪🇺 Novo €45 (Amazon.es) · Vinted usado €28–35 · importar ~€41
🇯🇵 Mercari vendidos ¥3.900–5.500
<razão em ≤ 3 frases>
Fontes: Amazon.es · Vinted · Mercari
```
- `run_claude`: `claude -p --output-format stream-json --verbose --model … --tools WebSearch --allowedTools WebSearch --strict-mcp-config --disable-slash-commands --no-session-persistence --setting-sources "" --system-prompt … --json-schema …`, prompt no stdin, `subprocess.Popen` lido linha a linha numa thread, timeout 300 s, resposta em `structured_output` do evento `result`. Erros → `PriceCheckError` com mensagem curta.
- Antes de implementar: teste real para confirmar que o Claude encontra preços europeus (novo e Vinted) para uma figura concreta; se a Vinted não aparecer por pesquisa web, reutilizar o cliente Vinted do VintedBot.

## 6. Fotos (fase 3)
- Testado (fase 0): imagem em base64 num bloco `image` via `--input-format stream-json --output-format stream-json --verbose --tools ""` + `--json-schema`; ~4 s, sem acesso a ficheiros. Leu corretamente uma etiqueta japonesa desfocada (nome, ¥4.800, 箱傷み → caixa danificada), sem confundir o número da Nendoroid com o preço.
- Usa a maior resolução que o Telegram envia. A legenda (opcional) tem prioridade: se tiver preço ou estado, esses valores ganham aos lidos na imagem.
- Devolve nome (pt/en), termo japonês, preço, estado, confiança; mostra "📷 Percebi: …" com «💡 Avaliar» e «✏️ Corrigir». Confiança baixa ou sem preço → pede correção.

## 7. Histórico e comandos (fase 4)
- Cada avaliação fica no SQLite; `/historico` mostra as últimas 10: data, nome, preço, veredicto.
- Comandos: `/start`, `/help`, `/id`, `/cambio`, `/historico`.

## Testes
- Puros: `parsing`, `rules`, `formatting`, normalização da chave da cache, cálculo do veredicto.
- Com fakes: `fx` (HTTP falso, relógio fixo), `storage` (`:memory:`), `appraisal` (runner falso que emite eventos), handlers do Telegram (bot/update falsos).

## Fases
0. ✅ Verificação: fotos e progresso em stream-json funcionam; Claude sozinho não chega a vendas concluídas japonesas; Mercari via `mercapi` funciona.
1. Esqueleto, config, parsing, contas, câmbio + `/cambio`, resposta imediata com «Corrigir», `/start` `/help` `/id`.
2. Avaliação por IA (Europa + Mercari) com progresso, fila, cache e limite diário.
3. Fotos da etiqueta.
4. Histórico, `README.md` / `CLAUDE.md`, `kaidokubot.sh` + `deploy.sh`, instalação no Pi.

## Decisões minhas (a rever)
- `CLAUDE_MODEL=sonnet`; timeout 300 s; limite 30/dia; dia de Tóquio.
- `httpx` para o câmbio (já é dependência do `mercapi`).
- O veredicto é calculado no código, não pelo Claude, para ser coerente e testável.
- Pedidos guardados no SQLite para os botões sobreviverem a reinícios.
