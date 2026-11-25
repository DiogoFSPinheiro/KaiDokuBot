# KaiDokuBot

買い得 (*kaidoku*) = "boa compra". Bot de Telegram pessoal que avalia, numa loja no Japão, se um artigo compensa face ao preço na Europa e se o preço é normal para o Japão. Também funciona em Portugal (preços em euros).

> ⚠️ Usa APIs internas (não oficiais) do Mercari, da Vinted e do KuantoKusta, e o Claude Code com a tua subscrição.

## Utilização

**Texto** — o nome e o preço (e o estado, se souberes):

    nendoroid frieren 4800
    zelda totk ¥3,980 sem caixa
    4.800円 pop up parade fern selado
    kadokawa light emilia 7000 caixa ok

- **Preço:** o número com ¥/円/yen; sem moeda, o último número que não seja uma medida (17 cm) nem uma escala (1/7).
- **Estado** (pt / en / ja): `selado`, `novo`, `usado`, `sem caixa`, `caixa danificada` — `未開封`, `中古`, `箱なし`, `箱傷み`, `caixa ok`…
- Escreve a **linha + personagem (+ nº)** (`nendoroid 2367`, `pop up parade fern`): é o que mais ajuda a identificar o produto.

Recebes logo as contas (¥4.800 → €27.35 em loja · €24.86 após reembolso) e, ~30 s depois, a avaliação:

    🟢 Compensa · poupas €29 (54%)
    💴 Máximo ¥8.300
    🇪🇺 Vinted ~€50 (12) · novo €55 (KuantoKusta) · importar ~€63
    🇯🇵 Mercari ¥3.900–4.500 ≈ €22–26 (8) · 👀 caro aqui
    🔍 Nendoroid Frieren 2367 · ver
    [📋 Detalhes] [🔄 Reavaliar] [✏️ Corrigir]

- 🟢 compensa / 🟡 pouca diferença / 🔴 não compensa face à alternativa europeia mais barata (novo, Vinted + portes, importar do Japão). Sem preços europeus, compara com os vendidos no Mercari (🟢 bom preço / 🟡 normal / 🔴 caro para o Japão).
- **«Máximo»** é o preço de montra a partir do qual deixa de compensar. 👀 = acima do que se vende no Mercari: vê noutras lojas.
- Os nomes das fontes são links para confirmares com um toque. **«📋 Detalhes»** mostra a razão, as fontes e os cêntimos.
- **«✏️ Corrigir»** muda o nome, o preço ou o estado e volta a avaliar.

**Foto** — da etiqueta ou da caixa, com o preço na legenda se quiseres. O bot mostra o que percebeu e só avalia quando carregas em **«💡 Avaliar»** (ou depois de corrigires).

**Em Portugal** — põe o preço em euros (`nendoroid frieren 35€`, `29,99 €`): compara só com a Europa (🟢 bom preço / 🟡 normal / 🔴 caro, ±10%).

Comandos: `/historico` (últimas 10 avaliações), `/cambio` (`/cambio 0.0058` fixa, `/cambio auto` volta ao automático), `/help`, `/id`.

## Contas e premissas

- **Tax-free por reembolso** (desde 1/11/2026): pagas o preço de montra e o imposto (10%) é devolvido no aeroporto — líquido = montra / 1.10. Abaixo de ¥5.500 numa loja num dia não há reembolso (o bot avisa).
- **Importar do Japão:** (¥ / 1.10 × câmbio + €15 de portes) × 1.23 + €2.65 CTT. **Vinted:** preço típico + €4 de portes.
- Premissas em `kaidokubot/rules.py` — confirmar antes da viagem.
- **Câmbio** do BCE (Frankfurter), atualizado 1× por dia; sem rede usa o último.

## Limites

- `MAX_AVALIACOES_DIA` (30) avaliações por dia (o dia vira à meia-noite de Tóquio); as respostas da cache não contam.
- Cache de `CACHE_DIAS` (30) dias por artigo e estado (o veredicto é recalculado para o preço atual). **«🔄 Reavaliar»** força uma pesquisa nova.

## Instalação no Raspberry Pi

Precisa de Python 3 com `venv` (`sudo apt install python3-venv`), de um sistema de 64 bits e do `claude` com sessão iniciada (`~/.local/bin/claude`).

1. Criar o bot no [@BotFather](https://t.me/BotFather) (`/newbot`) e copiar o token.
2. `git clone <url do repositório> ~/bots/KaiDokuBot && cd ~/bots/KaiDokuBot`
3. `cp .env.example .env` e preencher `TELEGRAM_TOKEN` (o resto tem valores por omissão).
4. `./kaidokubot.sh` → enviar `/id` ao bot → pôr o número em `ALLOWED_CHAT_ID` no `.env` → Ctrl+C.
5. `./kaidokubot.sh install` — serviço `systemd` que arranca com o Pi e reinicia se cair.
   - Log: `journalctl -u kaidokubot -f` · Estado: `sudo systemctl status kaidokubot`
6. Atualizar: `./deploy.sh` (git pull, dependências se mudaram, testes, e só reinicia se passarem). `./deploy.sh --force` reinicia mesmo sem alterações.

> Só pode haver **um** bot a correr com o mesmo token: desliga o do PC antes de ligar o do Pi (senão o Telegram dá `409 Conflict`).

## Desenvolvimento (Windows)

    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
    .venv\Scripts\python -m pytest -q
    .venv\Scripts\python -m kaidokubot.main

Desenho e decisões: `docs/superpowers/specs/2026-10-25-kaidokubot-design.md`.
