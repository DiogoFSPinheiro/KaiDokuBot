import asyncio

from kaidokubot.api import executar
from kaidokubot.fontes import Anuncio, FonteError


def _anuncios(n, preco=10.0):
    return [Anuncio(f"artigo {i}", preco + i, "novo", f"https://x/{i}") for i in range(n)]


class FakeMercari:
    def __init__(self, resposta=None):
        self.resposta = resposta if resposta is not None else (_anuncios(8, 3000), _anuncios(2, 4000))
        self.termos = []

    async def procurar(self, termo):
        self.termos.append(termo)
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return self.resposta


class FakeFonte:
    def __init__(self, resposta=None):
        self.resposta = resposta if resposta is not None else _anuncios(8)
        self.termos = []

    async def procurar(self, termo):
        self.termos.append(termo)
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return self.resposta


def _correr(argv, mercari=None, vinted=None, kuantokusta=None):
    mercari, vinted, kuantokusta = mercari or FakeMercari(), vinted or FakeFonte(), kuantokusta or FakeFonte()
    codigo, dados = asyncio.run(executar(argv, mercari, vinted, kuantokusta))
    return codigo, dados, (mercari, vinted, kuantokusta)


def test_precos_junta_as_tres_fontes():
    codigo, dados, (mercari, vinted, kuantokusta) = _correr(["precos", "--termo=Live A Live", "--termo-jp=ライブアライブ"])
    assert codigo == 0
    assert mercari.termos == ["ライブアライブ"]
    assert vinted.termos == ["Live A Live"] and kuantokusta.termos == ["Live A Live"]
    assert dados["termo"] == "Live A Live"
    assert len(dados["mercari"]["vendidos"]) == 5 and len(dados["mercari"]["a_venda"]) == 2
    assert len(dados["vinted"]) == 5 and len(dados["kuantokusta"]) == 5
    assert dados["mercari"]["vendidos"][0] == {
        "titulo": "artigo 0", "preco": 3000.0, "moeda": "JPY", "estado": "novo", "url": "https://x/0"
    }  # fmt: skip
    assert dados["vinted"][0]["moeda"] == "EUR" and dados["kuantokusta"][0]["moeda"] == "EUR"


def test_sem_termo_jp_o_mercari_usa_o_termo():
    _codigo, _dados, (mercari, _v, _k) = _correr(["precos", "--termo=Live A Live"])
    assert mercari.termos == ["Live A Live"]


def test_fonte_que_falha_vem_null():
    codigo, dados, _ = _correr(["precos", "--termo=x"], vinted=FakeFonte(FonteError("Vinted: HTTP 403")),
                               mercari=FakeMercari(RuntimeError("boom")))  # fmt: skip
    assert codigo == 0
    assert dados["vinted"] is None and dados["mercari"] is None
    assert len(dados["kuantokusta"]) == 5


def test_sem_resultados_e_lista_vazia():
    _codigo, dados, _ = _correr(["precos", "--termo=x"], kuantokusta=FakeFonte([]))
    assert dados["kuantokusta"] == []


def test_argumentos_invalidos():
    for argv in (
        ["precos"],
        ["precos", "--termo=   "],
        ["precos", "--termo=" + "a" * 101],
        ["precos", "--termo=x", "--termo-jp=" + "あ" * 101],
        ["outra"],
        [],
    ):
        codigo, dados, fontes = _correr(argv)
        assert codigo == 1, argv
        assert isinstance(dados.get("erro"), str) and dados["erro"], argv
        assert all(f.termos == [] for f in fontes), argv
