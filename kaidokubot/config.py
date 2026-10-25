from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    allowed_chat_id: int | None
    db_path: str
    # Caminho do Claude CLI para a avaliação por IA; None desliga a funcionalidade.
    claude_bin: str | None
    claude_model: str
    max_avaliacoes_dia: int
    margem_minima: int  # em %
    cache_dias: int
    # Avalia logo cada pedido (sem carregar em «Avaliar»).
    auto_avaliar: bool = True


def _int(env: Mapping[str, str], key: str, default: int | None, lo: int | None = None, hi: int | None = None):
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} tem de ser um número inteiro (recebi {raw!r}).") from exc
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise ConfigError(f"{key} tem de estar entre {lo} e {hi if hi is not None else '∞'} (recebi {value}).")
    return value


def load_settings(
    env: Mapping[str, str] | None = None, which: Callable[[str], str | None] = shutil.which
) -> Settings:
    if env is None:
        from dotenv import load_dotenv

        load_dotenv()
        env = os.environ
    token = (env.get("TELEGRAM_TOKEN") or "").strip()
    if not token:
        raise ConfigError("Falta TELEGRAM_TOKEN no .env (cria o bot no @BotFather).")
    return Settings(
        telegram_token=token,
        allowed_chat_id=_int(env, "ALLOWED_CHAT_ID", None),
        db_path=(env.get("DB_PATH") or "kaidokubot.db").strip(),
        claude_bin=(env.get("CLAUDE_BIN") or "").strip() or which("claude"),
        claude_model=(env.get("CLAUDE_MODEL") or "sonnet").strip(),
        max_avaliacoes_dia=_int(env, "MAX_AVALIACOES_DIA", 30, lo=0),
        margem_minima=_int(env, "MARGEM_MINIMA", 20, lo=0, hi=90),
        cache_dias=_int(env, "CACHE_DIAS", 30, lo=1),
        auto_avaliar=(env.get("AUTO_AVALIAR") or "1").strip() != "0",
    )
