from types import SimpleNamespace

from kaidokubot.fontes import Anuncio, anuncio_mercari, anuncio_vinted


def test_anuncio_mercari_traduz_o_estado():
    item = SimpleNamespace(name="ねんどろいど フリーレン", price=4500, item_condition_id=2)
    assert anuncio_mercari(item) == Anuncio("ねんどろいど フリーレン", 4500.0, "quase novo")


def test_anuncio_mercari_estado_desconhecido():
    assert anuncio_mercari(SimpleNamespace(name="x", price=1, item_condition_id=99)).estado == "?"


def test_anuncio_vinted_usa_preco_com_protecao_e_estado():
    raw = {
        "title": "Nendoroid Frieren 2367",
        "price": {"amount": "60.00", "currency_code": "EUR"},
        "total_item_price": {"amount": "63.70", "currency_code": "EUR"},
        "item_box": {"second_line": "Prematuro, até 44\xa0cm · Novo com etiquetas"},
    }
    assert anuncio_vinted(raw) == Anuncio("Nendoroid Frieren 2367", 63.7, "Novo com etiquetas")


def test_anuncio_vinted_sem_total_nem_estado():
    raw = {"title": "Fern", "price": {"amount": "18.00"}, "item_box": {}}
    assert anuncio_vinted(raw) == Anuncio("Fern", 18.0, "?")


def test_anuncio_vinted_preco_invalido_e_ignorado():
    assert anuncio_vinted({"title": "x", "price": {"amount": ""}}) is None
