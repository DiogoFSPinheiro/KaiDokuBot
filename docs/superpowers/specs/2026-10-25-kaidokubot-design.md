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
| `main.py` | arranque, logging, `ConfigError` → mensagem clara; cria as fontes e o avaliador |
| `config.py` | `.env` → `Settings` |
| `parsing.py` | texto → `Pedido(nome, preco_yen, estado)` (puro) |
| `rules.py` | premissas de dinheiro, contas, `Mercado` e cálculo do veredicto (puro) |
| `fx.py` | câmbio ¥→€ automático / manual (HTTP injetado) |
| `storage.py` | SQLite: pedidos, câmbio (kv), avaliações (histórico + cache + contagem diária) |
| `formatting.py` | todas as mensagens HTML (puro): resposta imediata, resumo compacto, detalhes |
| `commands.py` | comportamento do bot sem Telegram (`Resposta` com texto e botões), fluxo «Corrigir», `/cambio` |
| `claude.py` | `claude -p` em stream-json numa thread; avisa cada pesquisa web |
| `fontes.py` | Mercari (`mercapi`), Vinted (cliente adaptado do VintedBot), KuantoKusta |
| `appraisal.py` | avaliação por IA: cache, limite, fila, identificação, fontes, Claude, prompts e esquemas |
| `vision.py` | foto → pedido (fase 3) |
| `telegram_bot.py` | handlers, mensagem de progresso, avaliação automática |

### Configuração (`.env`)
`TELEGRAM_TOKEN` (obrigatório), `ALLOWED_CHAT_ID`, `CLAUDE_BIN` (por omissão `which claude`), `CLAUDE_MODEL=sonnet`, `AUTO_AVALIAR=1`, `MAX_AVALIACOES_DIA=30`, `MARGEM_MINIMA=20` (%), `CACHE_DIAS=30`, `DB_PATH=kaidokubot.db`. O dia do limite diário vira à meia-noite de `Asia/Tokyo`.

## 1. Entrada por texto (`parsing.py`)
Exemplos: `nendoroid frieren 4800`, `zelda totk ¥3,980 sem caixa`, `4.800円 pop up parade fern selado`.

- **Preço:** o yen não tem decimais, por isso `.` e `,` entre dígitos são sempre separadores de milhares (`4.800` = `4,800` = 4800). NFKC primeiro (dígitos e `￥` de largura total). Se algum número tiver `¥`, `円`, `yen` ou `JPY`, é esse o preço; senão é o último número que **não** seja uma medida (`17 cm`, `250 g`, `30㎝`, `センチ`, `号`) nem parte de uma escala (`1/7`). Válido entre ¥100 e ¥10 000 000; um número < 100 sem `¥` conta como "falta o preço" (ex.: «switch 2»).
- **Estado:** palavras-chave em pt-PT / inglês / japonês, sem distinguir maiúsculas. Estados: `selado`, `novo`, `usado`, `sem caixa`, `caixa danificada`, `desconhecido`. Com várias palavras ganha a mais específica: `caixa danificada` > `sem caixa` > `selado` > `usado` > `novo`; a expressão mais longa primeiro (`未開封` é selado, não `開封`).

  | Estado | Palavras-chave (exemplos) |
  |---|---|
  | selado | selado, sealed, misb, nib, 未開封, 新品未開封 |
  | novo | novo, nova, new, 新品, 未使用 |
  | usado | usado, used, aberto, opened, 中古, 開封, 開封品; e «caixa ok», «com caixa», completo, boxed, 箱あり (= usado e completo) |
  | sem caixa | sem caixa, no box, loose, 箱なし, 本体のみ |
  | caixa danificada | caixa danificada, damaged box, 箱傷み, 箱ダメージ, 箱潰れ |
- **Nome:** o texto sem o preço e sem as palavras de estado. Vazio → peço o nome.
- Editar a mensagem no Telegram conta como um pedido novo (útil para acrescentar um preço esquecido).

## 2. Regras de dinheiro (`rules.py`, comentário "premissas — confirmar antes da viagem")
- Desde 1/11/2026 o tax-free é por reembolso: pago o preço de montra (com 10%) e o imposto é devolvido após a verificação na alfândega à saída (até 90 dias). Assumo tudo reembolsável: `liquido = montra / 1.10`. `COMISSAO_REEMBOLSO = 0.0` (depende da loja; ex.: PPIH só cobra em dinheiro).
- Mínimo de ¥5.000 **sem imposto** por loja e por dia (somando as compras do dia na mesma loja). Se `montra < ¥5.500` a resposta diz: *"reembolso só se somares ≥ ¥5.500 nesta loja hoje"*.
- Formato: `¥4.800 → €27.35 em loja · €24.86 após reembolso (+€2.49)`.
- Importar do Japão = `(¥ / 1.10 × taxa + PORTES_IMPORTACAO_EUR) × (1 + IVA_PT) + TAXA_CTT_EUR` com `IVA_PT = 0.23`, `PORTES_IMPORTACAO_EUR = 15`, `TAXA_CTT_EUR = 2.65`.
- Vinted: preço típico + `PORTES_VINTED_EUR = 4`.

## 3. Câmbio (`fx.py`)
- Automático: `https://api.frankfurter.dev/v1/latest?base=JPY&symbols=EUR` (BCE, sem chave); alternativa `https://open.er-api.com/v6/latest/JPY`. Job a cada 6 h que só vai à rede se a última atualização tiver mais de 20 h; guardado no SQLite com a data e a fonte.
- Sem rede: usa o último guardado. Nunca houve câmbio: a resposta mostra só os ienes e "câmbio indisponível".
- `/cambio` mostra o valor, a data e se é automático ou manual; `/cambio 0.0058` fixa um valor manual (aceita `0,0058`); `/cambio auto` volta ao automático e atualiza já.

## 4. Resposta imediata (sem IA)
```
📦 Nendoroid Frieren
¥4.800 → €27.35 em loja · €24.86 após reembolso (+€2.49)
Estado: caixa danificada
ℹ️ reembolso só se somares ≥ ¥5.500 nesta loja hoje
[✏️ Corrigir]
```
- Cada pedido é guardado no SQLite (`pedidos`) para os botões sobreviverem a reinícios.
- **Texto → avaliação automática** (`AUTO_AVALIAR=1`, decisão do utilizador): a avaliação arranca logo por baixo, sem botão. Com `AUTO_AVALIAR=0` aparece «💡 Avaliar».
- **«✏️ Corrigir»** edita a própria mensagem (sem menus soltos): Nome / Preço / Estado / Cancelar. Nome e Preço: a mensagem seguinte substitui só esse campo (um texto que não seja só um preço cancela e conta como pedido novo). Estado: botões. Depois de corrigir, reavalia sozinho.

## 5. Avaliação por IA
Pipeline (uma mensagem de progresso que responde ao pedido e é editada no máximo a cada 3 s; ~30 s no total):
1. **Cache pelo texto** (`chave_cache(nome, estado)`, com `CACHE_VERSAO` para invalidar quando o processo muda; válida `CACHE_DIAS`). O preço não entra na chave: os dados de mercado são reutilizados e o veredicto recalculado para o preço atual.
2. **Limite diário** (`MAX_AVALIACOES_DIA`, dia de Tóquio; as respostas da cache não contam).
3. **Fila:** um pedido de IA de cada vez; "⏳ Na fila (posição N)…". Dentro da vez volta a ver a cache.
4. **Identificar o produto exato** (Claude + `WebSearch`, 1–2 pesquisas; "🔍 A identificar: …"): `fabricante`, `linha`, `personagem`, `referencia` (só nº de catálogo/versão), `referencia_url`, `termo_jp`, `termo_en`. Necessário porque «emilia 17cm» pode ser a KADOKAWA Collection LIGHT, uma Pop Up Parade ou uma figura de prémio.
5. **Cache pelo produto** (`linha|personagem|referencia`): o mesmo produto escrito de outra forma aproveita a avaliação.
6. **Fontes do bot, em paralelo** (testes 25/10: o Claude sozinho não chega a nenhuma; a Amazon, o eBay, o Suruga-ya e a Yahoo Auctions bloqueiam):
   - **Mercari** (`mercapi`): 40 vendidos e 20 à venda, com preço, estado e link;
   - **Vinted** (cliente adaptado do VintedBot): 30 anúncios, preço com proteção do comprador, estado e link (preços pedidos);
   - **KuantoKusta** (comparador português, JSON do `__NEXT_DATA__`; inclui a Amazon.es): 30 produtos com preço mínimo, nº de lojas e link. Sem resultados responde 404 → lista vazia. Não pesquisa por código de barras.
   Uma fonte em baixo → continua e avisa (`⚠️ Mercari indisponível`).
7. **Claude + `WebSearch`** (stream-json, "🌐 A pesquisar: …") recebe as listas com códigos (`[M1]`, `[V1]`, `[K1]`) e devolve no `--json-schema`: intervalos do Mercari e da Vinted no mesmo estado (com n e a mediana da Vinted), preço novo na Europa (de preferência o KuantoKusta, com o código; senão a web, só preços atuais da página da loja), preço numa loja online japonesa, cenários se o estado for desconhecido (os campos principais = usado), razão (≤ 2 frases) e fontes. Regras: só o mesmo produto (fabricante/linha/tamanho; o distribuidor europeu pode aparecer em vez do fabricante → correspondência provável), sem figuras de prémio se o artigo não for uma, intervalos mesmo com 1–2 comparáveis (o n diz a fiabilidade), nunca inventar.
8. **Veredicto no código** a partir do líquido em € e da alternativa europeia mais barata: novo na Europa; Vinted típico + portes (só com ≥ 2 anúncios); importar.
   - 🟢 compensa (poupança ≥ `MARGEM_MINIMA`), 🟡 pouca diferença, 🔴 não compensa; «Máximo ¥X» = montra que deixa exatamente a margem, arredondada à centena para baixo.
   - **Sem alternativa europeia → compara com o Mercari** (≥ 2 vendidos): 🟢 bom preço para o Japão (abaixo), 🟡 preço normal no Japão (dentro), 🔴 caro para o Japão (acima); «Máximo» = topo dos vendidos. Com menos → ⚪ incerto.
   - 👀 "caro aqui" se a montra passar o topo dos vendidos (≥ 3 vendidos).
9. **Resumo compacto** (a pedido do utilizador: nada de paredes de texto), com o link só no nome da fonte:
```
🟢 Compensa · poupas €29 (54%)
💴 Máximo ¥8.300
🇪🇺 Vinted ~€50 (12) · novo €55 (KuantoKusta) · importar ~€63
🇯🇵 Mercari ¥3.900–4.500 ≈ €22–26 (8) · 👀 caro aqui
🔍 Nendoroid Frieren 2367 · ver
❔ Sem estado: comparei como usado (✏️ Corrigir para afinar)
[📋 Detalhes] [🔄 Reavaliar] [✏️ Corrigir]
```
   «📋 Detalhes» mostra na mesma mensagem a versão completa (razão, fontes, cenários, cêntimos) e «📌 Resumo» volta. Erros: "❌ Não consegui avaliar: …" com «💡 Tentar outra vez»; não contam para o limite nem ficam na cache.
- Modelo: o Sonnet foi tão bom ou melhor que o Opus nos testes A/B e mais rápido (29 s vs 43–62 s).

## 6. Fotos (fase 3)
- Testado (fase 0): imagem em base64 num bloco `image` via `--input-format stream-json --output-format stream-json --verbose --tools ""` + `--json-schema`; ~4 s, sem acesso a ficheiros. Leu corretamente uma etiqueta japonesa desfocada (nome, ¥4.800, 箱傷み → caixa danificada), sem confundir o número da Nendoroid com o preço.
- Usa a maior resolução que o Telegram envia. A legenda (opcional) tem prioridade: se tiver preço ou estado, esses valores ganham aos lidos na imagem.
- Devolve nome (pt/en), termo japonês, preço, estado, confiança; mostra "📷 Percebi: …" com «💡 Avaliar» e «✏️ Corrigir». Confiança baixa ou sem preço → pede correção.
- **Só as fotos pedem confirmação** (decisão do utilizador, 25/10): a leitura da etiqueta pode falhar, por isso a avaliação só arranca quando carrego em «💡 Avaliar» (ou depois de corrigir). O texto é escrito por mim e avalia logo (`AUTO_AVALIAR=1`).

## 8. Modo Europa (preço em €)
- Para usar também em Portugal. Um preço com `€`/`eur`/`euros` (aceita cêntimos: `29,99€`; `1.299€` = mil e tal) cria um pedido em euros; sem moeda ou com ¥ fica o modo Japão.
- Resposta imediata só com o preço e o estado (sem câmbio nem tax-free).
- Avaliação sem Mercari nem importação: Vinted (típico + portes) e preço novo (KuantoKusta / web). Cache separada da do Japão.
- Veredicto face à alternativa europeia mais barata: 🟢 bom preço (≥ 10% abaixo), 🟡 preço normal (±10%), 🔴 caro (> 10% acima); `💶 Máximo` = essa alternativa.

## 7. Histórico e comandos (fase 4)
- Cada avaliação fica no SQLite; `/historico` mostra as últimas 10: data, nome, preço, veredicto.
- Comandos: `/start`, `/help`, `/id`, `/cambio`, `/historico`.

## Testes
- Puros: `parsing`, `rules`, `formatting`, normalização da chave da cache, cálculo do veredicto.
- Com fakes: `fx` (HTTP falso, relógio fixo), `storage` (`:memory:`), `appraisal` (runner falso que emite eventos), handlers do Telegram (bot/update falsos).

## Fases
0. ✅ Verificação: fotos e progresso em stream-json funcionam; Claude sozinho não chega a vendas concluídas japonesas; Mercari via `mercapi` funciona.
1. ✅ Esqueleto, config, parsing, contas, câmbio + `/cambio`, resposta imediata com «Corrigir», `/start` `/help` `/id`.
2. ✅ Avaliação por IA (identificação + Mercari + Vinted + KuantoKusta + web) com progresso, fila, cache e limite diário; avaliação automática do texto; resumo compacto com links.
3. ✅ Fotos da etiqueta ou da caixa (leitura ~4 s; a avaliação aproveita a identificação da foto).
4. ✅ `/historico`, `README.md` / `CLAUDE.md`, `kaidokubot.sh` + `deploy.sh`, guia de instalação no Pi.
5. ✅ Modo Europa (preço em €), pedido pelo utilizador depois da fase 3.

## Decisões minhas (a rever)
- `CLAUDE_MODEL=sonnet`; timeout 300 s; limite 30/dia; dia de Tóquio.
- `httpx` para o câmbio; `curl_cffi` para a Vinted e o KuantoKusta.
- O veredicto é calculado no código, não pelo Claude, para ser coerente e testável.
- Pedidos guardados no SQLite para os botões sobreviverem a reinícios.
