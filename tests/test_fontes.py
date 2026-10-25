from types import SimpleNamespace

from kaidokubot.fontes import Anuncio, anuncio_kuantokusta, anuncio_mercari, anuncio_vinted


def test_anuncio_mercari_traduz_o_estado():
    item = SimpleNamespace(id_="m123", name="ねんどろいど フリーレン", price=4500, item_condition_id=2)
    assert anuncio_mercari(item) == Anuncio("ねんどろいど フリーレン", 4500.0, "quase novo", "https://jp.mercari.com/item/m123")


def test_anuncio_mercari_estado_desconhecido():
    assert anuncio_mercari(SimpleNamespace(id_="m1", name="x", price=1, item_condition_id=99)).estado == "?"


def test_anuncio_vinted_usa_preco_com_protecao_e_estado():
    raw = {
        "title": "Nendoroid Frieren 2367",
        "price": {"amount": "60.00", "currency_code": "EUR"},
        "total_item_price": {"amount": "63.70", "currency_code": "EUR"},
        "item_box": {"second_line": "Prematuro, até 44\xa0cm · Novo com etiquetas"},
        "url": "https://www.vinted.pt/items/1-nendoroid",
    }
    assert anuncio_vinted(raw) == Anuncio(
        "Nendoroid Frieren 2367", 63.7, "Novo com etiquetas", "https://www.vinted.pt/items/1-nendoroid"
    )


def test_anuncio_vinted_sem_total_nem_estado():
    raw = {"title": "Fern", "price": {"amount": "18.00"}, "item_box": {}}
    assert anuncio_vinted(raw) == Anuncio("Fern", 18.0, "?")


def test_anuncio_vinted_preco_invalido_e_ignorado():
    assert anuncio_vinted({"title": "x", "price": {"amount": ""}}) is None


def test_anuncio_kuantokusta():
    raw = {"name": "Good Smile Company Estatua Emilia Re:ZERO 17cm", "priceMin": 44.6, "totalOffers": 1,
           "category": "Figuras de Coleção", "url": "/p/10618650/good-smile-emilia"}  # fmt: skip
    assert anuncio_kuantokusta(raw) == Anuncio(
        "Good Smile Company Estatua Emilia Re:ZERO 17cm", 44.6, "novo · 1 loja · Figuras de Coleção",
        "https://www.kuantokusta.pt/p/10618650/good-smile-emilia",
    )  # fmt: skip


def test_anuncio_kuantokusta_sem_preco_e_ignorado():
    assert anuncio_kuantokusta({"name": "x", "priceMin": None}) is None
