from __future__ import annotations

import asyncio
import logging
import sys

from kaidokubot.appraisal import Avaliador
from kaidokubot.claude import ClaudeCli
from kaidokubot.config import ConfigError, load_settings
from kaidokubot.fontes import Mercari, Vinted
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
    cambio = Cambio(storage, http)
    recursos: list = [http]
    avaliador = None
    if settings.claude_bin and settings.max_avaliacoes_dia > 0:
        mercari, vinted = Mercari(), Vinted()
        recursos += [mercari, vinted]
        avaliador = Avaliador(
            storage, cambio, ClaudeCli(settings.claude_bin, settings.claude_model), mercari, vinted,
            max_dia=settings.max_avaliacoes_dia, margem=settings.margem_minima, cache_dias=settings.cache_dias,
        )  # fmt: skip
        logging.info("Avaliação por IA ativa (%s, modelo %s)", settings.claude_bin, settings.claude_model)
    else:
        logging.warning("Avaliação por IA desligada (sem claude no PATH ou MAX_AVALIACOES_DIA=0)")
    app = build_application(settings, storage, cambio, recursos, avaliador)
    app.run_polling()


if __name__ == "__main__":
    main()
