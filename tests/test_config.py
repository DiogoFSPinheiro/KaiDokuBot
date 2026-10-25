import pytest

from kaidokubot.config import ConfigError, load_settings


def _no_claude(_name):
    return None


def test_defaults():
    s = load_settings({"TELEGRAM_TOKEN": "t"}, which=_no_claude)
    assert s.telegram_token == "t"
    assert (s.allowed_chat_id, s.db_path, s.claude_bin, s.claude_model) == (None, "kaidokubot.db", None, "sonnet")
    assert (s.max_avaliacoes_dia, s.margem_minima, s.cache_dias) == (30, 20, 30)


def test_values_are_parsed():
    s = load_settings(
        {
            "TELEGRAM_TOKEN": " t ",
            "ALLOWED_CHAT_ID": "-100123",
            "DB_PATH": "x.db",
            "CLAUDE_BIN": "/x/claude",
            "CLAUDE_MODEL": "opus",
            "MAX_AVALIACOES_DIA": "5",
            "MARGEM_MINIMA": "25",
            "CACHE_DIAS": "10",
        },
        which=_no_claude,
    )
    assert s.telegram_token == "t"
    assert s.allowed_chat_id == -100123
    assert (s.db_path, s.claude_bin, s.claude_model) == ("x.db", "/x/claude", "opus")
    assert (s.max_avaliacoes_dia, s.margem_minima, s.cache_dias) == (5, 25, 10)


def test_claude_found_on_path():
    s = load_settings({"TELEGRAM_TOKEN": "t"}, which=lambda name: f"/usr/bin/{name}")
    assert s.claude_bin == "/usr/bin/claude"


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"TELEGRAM_TOKEN": ""},
        {"TELEGRAM_TOKEN": "t", "ALLOWED_CHAT_ID": "abc"},
        {"TELEGRAM_TOKEN": "t", "MARGEM_MINIMA": "120"},
        {"TELEGRAM_TOKEN": "t", "MAX_AVALIACOES_DIA": "-1"},
        {"TELEGRAM_TOKEN": "t", "CACHE_DIAS": "0"},
    ],
)
def test_invalid_config_raises(env):
    with pytest.raises(ConfigError):
        load_settings(env, which=_no_claude)
