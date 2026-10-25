import pytest

from kaidokubot.parsing import ParseError, Pedido, parse_estado, parse_pedido, parse_preco


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("nendoroid frieren 4800", Pedido("nendoroid frieren", 4800, "desconhecido")),
        ("zelda totk ¥3,980 sem caixa", Pedido("zelda totk", 3980, "sem caixa")),
        ("4.800円 pop up parade fern selado", Pedido("pop up parade fern", 4800, "selado")),
        ("nendoroid 2367 frieren 4800", Pedido("nendoroid 2367 frieren", 4800, "desconhecido")),
        ("¥4800 nendoroid 2367", Pedido("nendoroid 2367", 4800, "desconhecido")),
        ("ps5 slim 39800 yen usado", Pedido("ps5 slim", 39800, "usado")),
        ("figura ４８００円 未開封", Pedido("figura", 4800, "selado")),
        ("figura ￥4,800 箱傷み 中古", Pedido("figura", 4800, "caixa danificada")),
        ("Peluche Chiikawa 1.200 NOVO", Pedido("Peluche Chiikawa", 1200, "novo")),
        ("Pokémon Scarlet 4,980 JPY caixa danificada", Pedido("Pokémon Scarlet", 4980, "caixa danificada")),
        ("nezuko nedoroid 5000 yen caixa ok", Pedido("nezuko nedoroid", 5000, "usado")),
        ("figura 3000 com caixa", Pedido("figura", 3000, "usado")),
        ("emilia re zero 17cm 7000", Pedido("emilia re zero 17cm", 7000, "desconhecido")),
        ("emilia 17 cm 7000", Pedido("emilia 17 cm", 7000, "desconhecido")),
        ("figura escala 1/7 12800", Pedido("figura escala 1/7", 12800, "desconhecido")),
        ("peluche 30㎝ 2500", Pedido("peluche 30cm", 2500, "desconhecido")),
        ("nendoroid 2367 in box", Pedido("nendoroid in box", 2367, "desconhecido")),
    ],
)
def test_parse_pedido(texto, esperado):
    assert parse_pedido(texto) == esperado


@pytest.mark.parametrize(
    "texto, estado",
    [
        ("新品未開封", "selado"),
        ("開封品", "usado"),
        ("usado sem caixa", "sem caixa"),
        ("novo selado", "selado"),
        ("damaged box", "caixa danificada"),
        ("loose", "sem caixa"),
        ("Usada", "usado"),
        ("箱なし", "sem caixa"),
        ("unused", "desconhecido"),  # "used" só conta como palavra inteira
        ("", "desconhecido"),
    ],
)
def test_parse_estado(texto, estado):
    assert parse_estado(texto) == estado


def test_sem_preco_da_erro():
    with pytest.raises(ParseError, match="preço"):
        parse_pedido("nendoroid frieren")


def test_sem_nome_da_erro():
    with pytest.raises(ParseError, match="nome"):
        parse_pedido("4800 selado")


@pytest.mark.parametrize("texto", ["figura 0", "figura 50", "figura 99999999", "figura ¥50"])
def test_preco_fora_de_limites(texto):
    with pytest.raises(ParseError, match="preço"):
        parse_pedido(texto)


def test_parse_preco_isolado():
    assert parse_preco("¥3.980") == 3980
    assert parse_preco("sem número") is None


@pytest.mark.parametrize(
    "texto",
    [
        "Good Smile Company Emilia Figura 17 cm re: Zero Starting Life in Another World kadokawa Collection Light",
        "figura escala 1/7",
        "peluche 30cm",
        "figura 250g",
    ],
)
def test_medidas_e_escalas_nao_sao_preco(texto):
    with pytest.raises(ParseError, match="Falta o preço"):
        parse_pedido(texto)



def test_numero_pequeno_e_falta_de_preco():
    with pytest.raises(ParseError, match="Falta o preço"):
        parse_pedido("Xenoblade Chronicles: Definitive Edition switch 2")



@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("nendoroid frieren 29,99€", Pedido("nendoroid frieren", 0, "desconhecido", 29.99)),
        ("nendoroid frieren €29.99 usado", Pedido("nendoroid frieren", 0, "usado", 29.99)),
        ("zelda totk 45 eur", Pedido("zelda totk", 0, "desconhecido", 45.0)),
        ("ps5 slim 1.299€", Pedido("ps5 slim", 0, "desconhecido", 1299.0)),
        ("pop up parade fern 30 euros selado", Pedido("pop up parade fern", 0, "selado", 30.0)),
        ("nendoroid 2367 35€", Pedido("nendoroid 2367", 0, "desconhecido", 35.0)),
    ],
)
def test_preco_em_euros(texto, esperado):
    pedido = parse_pedido(texto)
    assert pedido == esperado
    assert pedido.em_euros


def test_sem_moeda_continua_em_ienes():
    pedido = parse_pedido("nendoroid frieren 4800")
    assert (pedido.preco_yen, pedido.preco_eur, pedido.em_euros) == (4800, None, False)


@pytest.mark.parametrize("texto", ["figura 0€", "figura 200000€"])
def test_euros_fora_de_limites(texto):
    with pytest.raises(ParseError, match="preço"):
        parse_pedido(texto)


def test_parse_preco_moeda():
    from kaidokubot.parsing import parse_preco_moeda

    assert parse_preco_moeda("29,99 €") == (29.99, "EUR")
    assert parse_preco_moeda("¥3.980") == (3980, "JPY")
    assert parse_preco_moeda("5200") == (5200, "JPY")
    assert parse_preco_moeda("nada") is None
