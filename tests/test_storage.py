from kaidokubot.parsing import Pedido
from kaidokubot.storage import Storage

PEDIDO = Pedido("nendoroid frieren", 4800, "selado")


def test_pedido_ida_e_volta():
    storage = Storage()
    pedido_id = storage.add_pedido(1, PEDIDO, now=100.0)
    assert storage.get_pedido(pedido_id) == PEDIDO


def test_update_pedido():
    storage = Storage()
    pedido_id = storage.add_pedido(1, PEDIDO)
    storage.update_pedido(pedido_id, Pedido("nendoroid fern", 5200, "usado"))
    assert storage.get_pedido(pedido_id) == Pedido("nendoroid fern", 5200, "usado")


def test_pedido_inexistente_e_none():
    assert Storage().get_pedido(99) is None


def test_kv_set_get_apagar():
    storage = Storage()
    assert storage.get_kv("x") is None
    storage.set_kv("x", "1")
    storage.set_kv("x", "2")
    assert storage.get_kv("x") == "2"
    storage.set_kv("x", None)
    assert storage.get_kv("x") is None


def test_persistencia_em_ficheiro(tmp_path):
    path = str(tmp_path / "x.db")
    storage = Storage(path)
    pedido_id = storage.add_pedido(1, PEDIDO)
    storage.set_kv("fx_taxa", "0.0057")
    storage.close()
    storage = Storage(path)
    assert storage.get_pedido(pedido_id) == PEDIDO
    assert storage.get_kv("fx_taxa") == "0.0057"
    storage.close()


# --- avaliações, cache e limite (fase 2) ------------------------------------------------
from datetime import datetime, timezone  # noqa: E402

import pytest  # noqa: E402

from kaidokubot.storage import chave_cache, inicio_do_dia_tokyo  # noqa: E402


@pytest.mark.parametrize(
    "a, b",
    [(("Nendoroid  Frieren", "selado"), ("nendoroid frieren", "selado")),
     (("Pokémon Scarlet", "usado"), ("pokemon scarlet ", "usado")),
     (("ＰＯＰ ＵＰ", "novo"), ("pop up", "novo"))],
)  # fmt: skip
def test_chave_cache_normaliza(a, b):
    assert chave_cache(*a) == chave_cache(*b)


def test_chave_cache_depende_do_estado():
    assert chave_cache("nendoroid frieren", "selado") != chave_cache("nendoroid frieren", "usado")


def _avaliar(storage, chave, now, da_cache=False, mercado='{"x": 1}', dados_de=None):
    return storage.add_avaliacao(1, 1, PEDIDO, chave, mercado, "compensa", da_cache, dados_de=dados_de, now=now)


def test_cache_devolve_o_mais_recente_dentro_do_prazo():
    storage = Storage()
    _avaliar(storage, "k", 100.0, mercado='{"v": 1}')
    _avaliar(storage, "k", 200.0, mercado='{"v": 2}')
    _avaliar(storage, "k", 300.0, da_cache=True, mercado='{"v": 2}', dados_de=200.0)  # resposta da cache
    assert storage.cache("k", desde=50.0) == ('{"v": 2}', 200.0)
    assert storage.cache("k", desde=250.0) is None
    assert storage.cache("outra", desde=0.0) is None


def test_contar_avaliacoes_ignora_cache_e_antigas():
    storage = Storage()
    _avaliar(storage, "k", 100.0)
    _avaliar(storage, "k", 200.0)
    _avaliar(storage, "k", 210.0, da_cache=True)
    assert storage.contar_avaliacoes(desde=150.0) == 1


def test_ultimas_avaliacoes():
    storage = Storage()
    for i in range(12):
        _avaliar(storage, "k", float(i))
    ultimas = storage.ultimas_avaliacoes(10)
    assert len(ultimas) == 10
    assert ultimas[0]["criado_em"] == 11.0
    assert (ultimas[0]["nome"], ultimas[0]["preco_yen"], ultimas[0]["veredicto"]) == ("nendoroid frieren", 4800, "compensa")


def test_inicio_do_dia_tokyo():
    # 25/10 15:30 UTC = 26/10 00:30 em Tóquio -> o dia começou às 26/10 00:00 JST = 25/10 15:00 UTC.
    agora = datetime(2026, 10, 25, 15, 30, tzinfo=timezone.utc).timestamp()
    assert inicio_do_dia_tokyo(agora) == datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc).timestamp()



def test_get_avaliacao():
    storage = Storage()
    aval_id = _avaliar(storage, "k", 200.0, da_cache=True, mercado='{"v": 2}', dados_de=100.0)
    a = storage.get_avaliacao(aval_id)
    assert (a.pedido_id, a.pedido, a.mercado_json, a.dados_de) == (1, PEDIDO, '{"v": 2}', 100.0)
    assert storage.get_avaliacao(99) is None


def test_migra_tabela_antiga_sem_dados_de(tmp_path):
    import sqlite3

    path = str(tmp_path / "velho.db")
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE avaliacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, pedido_id INTEGER NOT NULL, "
        "nome TEXT NOT NULL, preco_yen INTEGER NOT NULL, estado TEXT NOT NULL, chave TEXT NOT NULL, mercado_json TEXT NOT NULL, "
        "veredicto TEXT NOT NULL, da_cache INTEGER NOT NULL, criado_em REAL NOT NULL)"
    )
    db.commit()
    db.close()
    storage = Storage(path)
    aval_id = _avaliar(storage, "k", 5.0, dados_de=1.0)
    assert storage.get_avaliacao(aval_id).dados_de == 1.0



def test_chave_cache_tem_versao():
    assert chave_cache("x", "usado").startswith("v2|")


def test_cache_por_produto():
    storage = Storage()
    storage.add_avaliacao(1, 1, PEDIDO, "k1", '{"v": 1}', "compensa", False, chave_produto="p", now=100.0)
    assert storage.cache_produto("p", desde=50.0) == ('{"v": 1}', 100.0)
    assert storage.cache_produto("outro", desde=0.0) is None
