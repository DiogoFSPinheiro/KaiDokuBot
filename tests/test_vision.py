import pytest

from kaidokubot.vision import Leitura, ler_foto, leitura_de

DADOS = {
    "nome": "Nendoroid Frieren", "fabricante": "Good Smile Company", "linha": "Nendoroid", "personagem": "Frieren",
    "referencia": "2367", "termo_jp": "ねんどろいど フリーレン", "termo_en": "nendoroid frieren 2367",
    "preco_yen": 4800, "estado": "caixa danificada", "confianca": "alta",
}  # fmt: skip


def test_leitura_da_foto():
    leitura = leitura_de(DADOS, None)
    assert (leitura.nome, leitura.preco_yen, leitura.estado, leitura.confianca) == (
        "Nendoroid Frieren", 4800, "caixa danificada", "alta"
    )
    assert leitura.termos == {
        "fabricante": "Good Smile Company", "linha": "Nendoroid", "personagem": "Frieren", "referencia": "2367",
        "referencia_url": None, "termo_jp": "ねんどろいど フリーレン", "termo_en": "nendoroid frieren 2367",
    }  # fmt: skip


def test_legenda_ganha_ao_que_foi_lido():
    leitura = leitura_de(DADOS, "3980 selado")
    assert (leitura.preco_yen, leitura.estado) == (3980, "selado")


def test_legenda_so_com_estado_mantem_o_preco_lido():
    assert leitura_de(DADOS, "usado").preco_yen == 4800


@pytest.mark.parametrize("preco", [None, 0, 50, 99_999_999, "abc"])
def test_preco_ilegivel_ou_absurdo_fica_none(preco):
    assert leitura_de({**DADOS, "preco_yen": preco}, None).preco_yen is None


def test_estado_invalido_fica_desconhecido():
    assert leitura_de({**DADOS, "estado": "meh"}, None).estado == "desconhecido"


def test_sem_nome_usa_linha_e_personagem():
    assert leitura_de({**DADOS, "nome": ""}, None).nome == "Nendoroid Frieren 2367"


class _Runner:
    def __init__(self):
        self.chamadas = []

    async def run(self, prompt, schema, *, system, tools="", on_search=None, imagem=None, media_type="image/jpeg"):
        self.chamadas.append((schema["title"], tools, imagem, media_type))
        return DADOS


async def test_ler_foto_passa_a_imagem_ao_claude_sem_ferramentas():
    runner = _Runner()
    leitura = await ler_foto(runner, b"img", "image/png", "4500")
    assert runner.chamadas == [("foto", "", b"img", "image/png")]
    assert isinstance(leitura, Leitura) and leitura.preco_yen == 4500



def test_jogo_sem_personagem_usa_o_titulo():
    dados = {**DADOS, "nome": "Xenoblade Chronicles 2 Torna", "fabricante": "Nintendo", "linha": "Nintendo Switch",
             "personagem": "", "referencia": ""}  # fmt: skip
    assert leitura_de(dados, None).termos["personagem"] == "Xenoblade Chronicles 2 Torna"


def test_legenda_em_euros():
    leitura = leitura_de(DADOS, "30€")
    assert (leitura.preco_yen, leitura.preco_eur) == (None, 30.0)
