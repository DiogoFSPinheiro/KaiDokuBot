#!/usr/bin/env bash
# Arranca o KaiDokuBot no Linux (ex.: Raspberry Pi): cria o venv e instala dependências na primeira vez.
#   ./kaidokubot.sh           arranca em primeiro plano (Ctrl+C para parar)
#   ./kaidokubot.sh install   instala como serviço systemd: arranca com o Pi e reinicia se cair
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

if [ ! -f .env ]; then
    echo "Falta o ficheiro .env. Copia o .env.example para .env e preenche o TELEGRAM_TOKEN."
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    echo "A criar o ambiente virtual..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

if [ "${1:-}" = "install" ]; then
    # O PATH inclui ~/.local/bin para o serviço encontrar o claude (avaliação por IA e fotos).
    sudo tee /etc/systemd/system/kaidokubot.service >/dev/null <<EOF
[Unit]
Description=KaiDokuBot
Wants=network-online.target
After=network-online.target

[Service]
User=$USER
WorkingDirectory=$PWD
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart=$PWD/.venv/bin/python -m kaidokubot.main
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable --now kaidokubot
    echo "Serviço instalado e a correr. Ver o log: journalctl -u kaidokubot -f"
    exit 0
fi

exec .venv/bin/python -m kaidokubot.main
