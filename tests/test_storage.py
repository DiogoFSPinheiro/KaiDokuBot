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
