from __future__ import annotations

import asyncio
import logging
import sys

from kaidokubot.config import ConfigError, load_settings
from kaidokubot.fx import Cambio, HttpJson
from kaidokubot.storage import Storage
from kaidokubot.telegram_bot import build_application


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        settings = load_settings()
    except ConfigError as exc:
        sys.exit(f"Erro de configuração: {exc}")
    storage = Storage(settings.db_path)
    http = HttpJson()
    app = build_application(settings, storage, Cambio(storage, http), http)
    app.run_polling()


if __name__ == "__main__":
    main()
