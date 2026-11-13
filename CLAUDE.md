# KaiDokuBot

Bot Telegram pessoal (um só `ALLOWED_CHAT_ID`) que avalia preços de merch japonesa numa loja no Japão face à Europa e ao Mercari; em euros, só face à Europa. Código, comentários, mensagens e docs em pt-PT. Desenho completo: `docs/superpowers/specs/2026-10-25-kaidokubot-design.md`.

## Comandos
- `.venv/Scripts/python.exe -m pytest -q` — testes (nunca usam rede, Telegram nem Claude: fakes em `tests/fakes.py`)
- `.venv/Scripts/python.exe -m kaidokubot.main` — arranca o bot (precisa de `.env`); no Windows usar `-X utf8` se redirecionares o log
- `.venv/Scripts/python.exe -X utf8 -m kaidokubot.fontes "<termo jp>" "<termo en>"` — smoke test real do Mercari, Vinted e KuantoKusta
- No Pi: `./kaidokubot.sh install` (serviço `kaidokubot`), `./deploy.sh`, `journalctl -u kaidokubot -f`
- Commits em `main`, sem `Co-Authored-By`; **sem `git push`** (o utilizador faz)

## Arquitetura
- `parsing.py` (texto → `Pedido`; € → `preco_eur`, modo Europa) · `rules.py` (premissas, `Mercado`, veredictos) · `formatting.py` (todo o HTML) — puros, TDD
- `commands.py` — comportamento sem Telegram (`Resposta` com texto, botões e `pedido_id` para a avaliação automática)
- `appraisal.py` — cache → limite → fila → identificar produto (ou termos da foto) → cache pelo produto → fontes em paralelo → Claude → veredicto no código
- `fontes.py` — Mercari (`mercapi`), Vinted (cliente adaptado do VintedBot, `curl_cffi`), KuantoKusta (`__NEXT_DATA__`; 404 = sem resultados)
- `claude.py` — `claude -p --output-format stream-json --verbose --json-schema …` numa thread (Selector loop do Windows não suporta subprocessos asyncio); imagens via `--input-format stream-json` em base64; `--bare` não serve (exige API key)
- `vision.py` — foto → `Leitura` (a legenda ganha ao preço/estado lidos)
- `api.py` — `python -m kaidokubot.api precos --termo=T [--termo-jp=J]`: a Wintermute vê preços (Mercari, Vinted, KuantoKusta, 5 por fonte) numa linha de JSON; só leitura, sem Telegram, Claude nem DB; fonte que falha = `null`

## Lições (não óbvias)
- O Claude sozinho não chega a preços reais: Mercari é JS, Yahoo Auctions/Suruga-ya bloqueiam Portugal (403), Amazon/eBay bloqueiam bots. Por isso o bot vai buscar Mercari, Vinted e KuantoKusta e dá-os ao Claude com códigos (`[M1]`, `[V1]`, `[K1]`) que viram links.
- Identificar o produto exato antes de pesquisar é o que mais pesa no resultado («emilia 17cm» ≠ figura de prémio). A chave da cache pelo produto usa só `linha|personagem|referencia` (as descrições do Claude variam).
- Nos anúncios europeus aparece o distribuidor (Good Smile) em vez do fabricante (KADOKAWA): o prompt aceita isso como correspondência provável.
- Ao mudar o processo de avaliação, subir `CACHE_VERSAO` em `storage.py`.
- Sonnet ≥ Opus nos testes A/B e mais rápido; `CLAUDE_MODEL` no `.env`.
- Ao gerar código com heredocs/Python, cuidado com `\n` dentro de strings (já partiu `formatting.py` várias vezes): preferir o Edit.
