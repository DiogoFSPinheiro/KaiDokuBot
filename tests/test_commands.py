import pytest

from kaidokubot.commands import Commands, Resposta
from kaidokubot.fx import URL_BCE, Cambio
from kaidokubot.parsing import Pedido
from kaidokubot.storage import Storage
from tests.fakes import FakeClock, FakeHttp

BCE = {"amount": 1.0, "base": "JPY", "date": "2026-10-23", "rates": {"EUR": 0.0057}}
CHAT = 1


@pytest.fixture
def storage():
    return Storage()


@pytest.fixture
def commands(storage):
    cambio = Cambio(storage, FakeHttp({URL_BCE: BCE}), now=FakeClock())
    cambio.definir_manual(0.0056979)
    return Commands(storage, cambio)


def test_texto_valido_guarda_pedido_e_responde(commands, storage):
    r = commands.texto(CHAT, "nendoroid frieren 4800")
    assert r.texto.splitlines()[:2] == [
        "📦 <b>nendoroid frieren</b>",
        "¥4.800 → €27.35 em loja · €24.86 após reembolso (+€2.49)",
    ]
    assert r.botoes == [[("✏️ Corrigir", "fix:1")]]
    assert storage.get_pedido(1) == Pedido("nendoroid frieren", 4800, "desconhecido")


def test_texto_invalido_explica(commands):
    r = commands.texto(CHAT, "nendoroid frieren")
    assert "preço" in r.texto
    assert r.botoes == []


def test_menu_corrigir(commands):
    commands.texto(CHAT, "nendoroid frieren 4800")
    r = commands.menu_corrigir(1)
    datas = [data for linha in r.botoes for _, data in linha]
    assert datas == ["fixf:1:nome", "fixf:1:preco", "fixf:1:estado", "fixx:1"]


def test_corrigir_preco(commands, storage):
    commands.texto(CHAT, "nendoroid frieren 4800")
    assert "preço" in commands.pedir_campo(CHAT, 1, "preco").texto
    r = commands.texto(CHAT, "¥5,200")
    assert storage.get_pedido(1).preco_yen == 5200
    assert "¥5.200" in r.texto
    assert r.botoes == [[("✏️ Corrigir", "fix:1")]]


def test_corrigir_nome(commands, storage):
    commands.texto(CHAT, "nendoroid frieren 4800")
    commands.pedir_campo(CHAT, 1, "nome")
    commands.texto(CHAT, "  Nendoroid   Fern ")
    assert storage.get_pedido(1) == Pedido("Nendoroid Fern", 4800, "desconhecido")


def test_corrigir_estado(commands, storage):
    commands.texto(CHAT, "nendoroid frieren 4800")
    r = commands.pedir_campo(CHAT, 1, "estado")
    datas = [data for linha in r.botoes for _, data in linha]
    assert datas == [f"st:1:{i}" for i in range(6)] + ["fixx:1"]
    r = commands.definir_estado(1, 0)
    assert storage.get_pedido(1).estado == "selado"
    assert "Estado: selado" in r.texto


def test_preco_sem_numero_cancela_e_trata_como_novo(commands, storage):
    commands.texto(CHAT, "nendoroid frieren 4800")
    commands.pedir_campo(CHAT, 1, "preco")
    r = commands.texto(CHAT, "zelda 3980")
    assert storage.get_pedido(1).preco_yen == 4800
    assert storage.get_pedido(2) == Pedido("zelda", 3980, "desconhecido")
    assert r.botoes == [[("✏️ Corrigir", "fix:2")]]


def test_preco_fora_de_limites_explica_e_continua_a_espera(commands, storage):
    commands.texto(CHAT, "nendoroid frieren 4800")
    commands.pedir_campo(CHAT, 1, "preco")
    assert "preço" in commands.texto(CHAT, "0").texto
    commands.texto(CHAT, "5000")
    assert storage.get_pedido(1).preco_yen == 5000


def test_pedido_inexistente(commands):
    for r in (commands.menu_corrigir(99), commands.definir_estado(99, 0), commands.pedir_campo(CHAT, 99, "nome")):
        assert r.texto.startswith("Já não tenho esse pedido")


def test_estado_invalido(commands):
    commands.texto(CHAT, "nendoroid frieren 4800")
    assert commands.definir_estado(1, 9).texto.startswith("Estado inválido")


def test_cancelar(commands, storage):
    commands.texto(CHAT, "nendoroid frieren 4800")
    commands.pedir_campo(CHAT, 1, "nome")
    r = commands.cancelar(CHAT, 1)
    assert isinstance(r, Resposta)
    assert r.texto.startswith("📦 <b>nendoroid frieren</b>")
    assert r.botoes == commands.botoes_pedido(1)
    commands.texto(CHAT, "abc 100")
    assert storage.get_pedido(1).nome == "nendoroid frieren"
    assert storage.get_pedido(2).nome == "abc"


async def test_cambio_mostrar_manual_e_auto(commands):
    assert (await commands.cambio([])).splitlines() == ["💱 1 ¥ = €0.0056979 (manual)", "¥1.000 = €5.70"]
    assert "€0.006 (manual)" in await commands.cambio(["0,006"])
    texto = await commands.cambio(["auto"])
    assert "€0.0057 (BCE, 2026-10-23)" in texto
    assert (await commands.cambio(["x"])).startswith("Uso:")


async def test_cambio_indisponivel(storage):
    commands = Commands(storage, Cambio(storage, FakeHttp(), now=FakeClock()))
    assert "indisponível" in await commands.cambio([])
    assert "câmbio indisponível" in commands.texto(CHAT, "zelda 3980").texto


def test_cancelar_pedido_inexistente(commands):
    assert commands.cancelar(CHAT, 99).texto.startswith("Já não tenho esse pedido")


def test_botoes_com_avaliacao(storage):
    commands = Commands(storage, Cambio(storage, FakeHttp(), now=FakeClock()), avaliacao=True)
    r = commands.texto(CHAT, "nendoroid frieren 4800")
    assert r.botoes == [[("💡 Avaliar", "av:1"), ("✏️ Corrigir", "fix:1")]]


def test_pedido_id_so_nas_respostas_de_um_pedido(commands):
    assert commands.texto(CHAT, "nendoroid frieren 4800").pedido_id == 1
    assert commands.texto(CHAT, "sem preço").pedido_id is None
    assert commands.menu_corrigir(1).pedido_id is None
    assert commands.definir_estado(1, 0).pedido_id == 1
    commands.pedir_campo(CHAT, 1, "preco")
    assert commands.texto(CHAT, "5000").pedido_id == 1



def _leitura(preco=4800, confianca="alta", estado="caixa danificada"):
    from kaidokubot.vision import Leitura

    return Leitura("Nendoroid Frieren", preco, estado, confianca, {"linha": "Nendoroid", "personagem": "Frieren"})


def test_foto_mostra_o_que_percebeu_e_nao_avalia_sozinha(storage):
    commands = Commands(storage, Cambio(storage, FakeHttp(), now=FakeClock()), avaliacao=False)
    r = commands.foto(CHAT, _leitura())
    assert r.texto.splitlines()[0] == "📷 Percebi:"
    assert "📦 <b>Nendoroid Frieren</b>" in r.texto and "Estado: caixa danificada" in r.texto
    assert r.botoes == [[("💡 Avaliar", "av:1"), ("✏️ Corrigir", "fix:1")]]
    assert r.pedido_id is None
    assert storage.get_termos(1) == {"linha": "Nendoroid", "personagem": "Frieren"}


def test_foto_com_pouca_confianca_avisa(commands):
    assert "⚠️ Não tenho a certeza" in commands.foto(CHAT, _leitura(confianca="baixa")).texto


def test_foto_sem_preco_pergunta_e_a_resposta_completa_o_pedido(commands, storage):
    r = commands.foto(CHAT, _leitura(preco=None))
    assert "Não consegui ler o preço" in r.texto
    r = commands.texto(CHAT, "4800")
    assert storage.get_pedido(1).preco_yen == 4800
    assert r.pedido_id == 1  # depois de completar, avalia sozinho


def test_corrigir_o_nome_apaga_a_identificacao(commands, storage):
    commands.foto(CHAT, _leitura())
    commands.pedir_campo(CHAT, 1, "nome")
    commands.texto(CHAT, "Nendoroid Fern")
    assert storage.get_termos(1) is None


def test_corrigir_o_estado_mantem_a_identificacao(commands, storage):
    commands.foto(CHAT, _leitura())
    commands.definir_estado(1, 0)
    assert storage.get_termos(1) is not None



def test_texto_em_euros(commands, storage):
    r = commands.texto(CHAT, "nendoroid frieren 29,99€")
    assert r.texto.splitlines()[0] == "📦 <b>nendoroid frieren</b> · €29.99"
    assert storage.get_pedido(1).preco_eur == 29.99


def test_corrigir_preco_para_euros(commands, storage):
    commands.texto(CHAT, "nendoroid frieren 4800")
    commands.pedir_campo(CHAT, 1, "preco")
    commands.texto(CHAT, "30€")
    assert (storage.get_pedido(1).preco_eur, storage.get_pedido(1).preco_yen) == (30.0, 0)


def test_foto_com_legenda_em_euros(commands, storage):
    from kaidokubot.vision import Leitura

    r = commands.foto(CHAT, Leitura("Nendoroid Frieren", None, "usado", "alta", {}, preco_eur=30.0))
    assert "€30.00" in r.texto
    assert storage.get_pedido(1).preco_eur == 30.0


def test_historico(commands, storage):
    assert commands.historico().texto == "Ainda não há avaliações."
    storage.add_avaliacao(CHAT, 1, Pedido("zelda", 3980, "usado"), "k", "{}", "nao", False, now=1_000_000.0)
    assert "🔴" in commands.historico().texto and "zelda · ¥3.980" in commands.historico().texto
