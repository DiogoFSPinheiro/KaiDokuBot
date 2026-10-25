import json

import pytest

from kaidokubot.claude import ClaudeError, ler_stream


def _linha(**evento):
    return json.dumps(evento, ensure_ascii=False) + "\n"


def _tool_use(name, **entrada):
    return _linha(type="assistant", message={"content": [{"type": "tool_use", "name": name, "input": entrada}]})


INIT = _linha(type="system", subtype="init")
RESULT = _linha(type="result", subtype="success", is_error=False, structured_output={"ok": 1})


def test_devolve_structured_output_e_avisa_pesquisas():
    pesquisas = []
    linhas = [
        INIT,
        _tool_use("WebSearch", query="ねんどろいど フリーレン", mode="standard"),
        _linha(type="user", message={"content": []}),
        _tool_use("WebSearch", query="nendoroid frieren prix"),
        _tool_use("StructuredOutput", ok=1),
        "\n",
        RESULT,
    ]
    assert ler_stream(linhas, pesquisas.append) == {"ok": 1}
    assert pesquisas == ["ねんどろいど フリーレン", "nendoroid frieren prix"]


def test_sem_on_search_e_linhas_invalidas_ignoradas():
    assert ler_stream([INIT, "isto não é json\n", RESULT], None) == {"ok": 1}


def test_erro_do_claude():
    linhas = [_linha(type="result", subtype="error_max_turns", is_error=True, result="limite")]
    with pytest.raises(ClaudeError, match="limite"):
        ler_stream(linhas, None)


def test_sem_resultado():
    with pytest.raises(ClaudeError, match="sem resposta"):
        ler_stream([INIT], None)


def test_resultado_sem_structured_output():
    with pytest.raises(ClaudeError):
        ler_stream([_linha(type="result", subtype="success", is_error=False, result="texto")], None)
