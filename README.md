# KaiDokuBot

買い得 (*kaidoku*) = "a good buy". Personal Telegram bot that tells you, while standing in a shop in Japan, whether an item is worth buying there instead of in Europe, and whether the price is normal for Japan. Also works in Portugal (prices in euros).

> ⚠️ Uses internal (unofficial) APIs from Mercari, Vinted and KuantoKusta, and Claude Code with your own subscription. If any service changes, that part stops working until it is adapted.

## Usage

**Text:** the name and price (and condition, if you know it):

    nendoroid frieren 4800
    zelda totk ¥3,980 sem caixa
    4.800円 pop up parade fern selado
    kadokawa light emilia 7000 caixa ok

- **Price:** the number with ¥/円/yen; with no currency, the last number that isn't a measurement (17 cm) or a scale (1/7).
- **Condition** (pt / en / ja): sealed, new, used, no box, damaged box: `selado`, `novo`, `usado`, `sem caixa`, `caixa danificada`, `未開封`, `中古`, `箱なし`, `箱傷み`, `caixa ok`…
- Write the **line + character (+ number)** (`nendoroid 2367`, `pop up parade fern`): it's what helps most to identify the product.

You get the maths straight away (¥4,800 → €27.35 in store · €24.86 after refund) and, ~30 s later, the verdict (the bot replies in Portuguese):

    🟢 Compensa · poupas €29 (54%)
    💴 Máximo ¥8.300
    🇪🇺 Vinted ~€50 (12) · novo €55 (KuantoKusta) · importar ~€63
    🇯🇵 Mercari ¥3.900–4.500 ≈ €22–26 (8) · 👀 caro aqui
    🔍 Nendoroid Frieren 2367 · ver
    [📋 Detalhes] [🔄 Reavaliar] [✏️ Corrigir]

- 🟢 worth it / 🟡 small difference / 🔴 not worth it, compared with the cheapest European alternative (new, Vinted + shipping, or importing from Japan). With no European prices, it compares with sold listings on Mercari (🟢 good price / 🟡 normal / 🔴 expensive for Japan).
- **Máximo** is the shelf price above which it stops being worth it. 👀 = above what sells on Mercari: check other shops.
- Source names are links, so you can confirm with one tap. **📋 Detalhes** shows the reasoning, sources and exact amounts.
- **✏️ Corrigir** changes the name, price or condition and re-evaluates.

**Photo:** of the label or box, with the price in the caption if you like. The bot shows what it understood and only evaluates when you tap **💡 Avaliar** (or after you correct it).

**In Portugal:** give the price in euros (`nendoroid frieren 35€`, `29,99 €`). It compares with Europe only (🟢 good price / 🟡 normal / 🔴 expensive, ±10%).

Commands: `/historico` (last 10 evaluations), `/cambio` (`/cambio 0.0058` sets a fixed rate, `/cambio auto` goes back to automatic), `/help`, `/id`.

## Calculations and assumptions

- **Tax-free by refund** (since 1/11/2026): you pay the shelf price and the tax (10%) is refunded at the airport, so net = shelf / 1.10. Below ¥5,500 per shop per day there's no refund (the bot warns you).
- **Import from Japan:** (¥ / 1.10 × FX rate + €15 shipping) × 1.23 + €2.65 CTT fee. **Vinted:** typical price + €4 shipping.
- Assumptions live in `kaidokubot/rules.py`. Check them before travelling.
- **FX rate** from the ECB (via Frankfurter), updated once a day; offline, it uses the last known rate.

## Limits

- `MAX_AVALIACOES_DIA` (30) evaluations per day (the day rolls over at midnight Tokyo time); cached answers don't count.
- Cache of `CACHE_DIAS` (30) days per item and condition (the verdict is recalculated for the current price). **🔄 Reavaliar** forces a fresh search.

## Installation on Raspberry Pi

Requires Python 3 with `venv` (`sudo apt install python3-venv`), a 64-bit OS, and `claude` logged in (`~/.local/bin/claude`).

1. Create the bot with [@BotFather](https://t.me/BotFather) (`/newbot`) and copy the token.
2. `git clone <repository url> ~/bots/KaiDokuBot && cd ~/bots/KaiDokuBot`
3. `cp .env.example .env` and fill in `TELEGRAM_TOKEN` (the rest has defaults).
4. `./kaidokubot.sh` → send `/id` to the bot → put the number in `ALLOWED_CHAT_ID` in `.env` → Ctrl+C.
5. `./kaidokubot.sh install`: `systemd` service that starts with the Pi and restarts if it crashes.
   - Logs: `journalctl -u kaidokubot -f` · Status: `sudo systemctl status kaidokubot`
6. Update: `./deploy.sh` (git pull, dependencies if they changed, tests, and only restarts if they pass). `./deploy.sh --force` restarts even with no changes.

> Only **one** bot can run with the same token: stop the one on your PC before starting the one on the Pi (otherwise Telegram returns `409 Conflict`).

## Development (Windows)

    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
    .venv\Scripts\python -m pytest -q
    .venv\Scripts\python -m kaidokubot.main

Design and decisions: `docs/superpowers/specs/2026-10-25-kaidokubot-design.md`.
