import pytest

from kaidokubot.fx import URL_ALTERNATIVA, URL_BCE, Cambio, EstadoCambio, parse_taxa
from kaidokubot.storage import Storage
from tests.fakes import FakeClock, FakeHttp

BCE = {"amount": 1.0, "base": "JPY", "date": "2026-10-23", "rates": {"EUR": 0.0057}}
ALT = {"result": "success", "time_last_update_utc": "Fri, 23 Oct 2026 00:02:31 +0000", "rates": {"EUR": 0.0058}}


def _cambio(respostas, storage=None, clock=None):
    http = FakeHttp(respostas)
    return Cambio(storage or Storage(), http, now=clock or FakeClock()), http


async def test_atualiza_do_bce():
    storage = Storage()
    cambio, _ = _cambio({URL_BCE: BCE}, storage)
    assert await cambio.atualizar() == EstadoCambio(0.0057, "2026-10-23", "BCE", False)
    assert cambio.taxa() == 0.0057
    assert storage.get_kv("fx_taxa") == "0.0057"


async def test_usa_alternativa_se_bce_falhar():
    cambio, _ = _cambio({URL_BCE: RuntimeError("down"), URL_ALTERNATIVA: ALT})
    assert await cambio.atualizar() == EstadoCambio(0.0058, "2026-10-23", "open.er-api", False)


async def test_resposta_invalida_passa_a_alternativa():
    cambio, _ = _cambio({URL_BCE: {"rates": {}}, URL_ALTERNATIVA: ALT})
    assert (await cambio.atualizar()).taxa == 0.0058


async def test_sem_rede_mantem_ultimo_guardado():
    storage = Storage()
    cambio, http = _cambio({URL_BCE: BCE}, storage)
    await cambio.atualizar()
    http.respostas = {}
    estado = await cambio.atualizar(force=True)
    assert (estado.taxa, estado.data) == (0.0057, "2026-10-23")


async def test_sem_rede_e_sem_historico():
    cambio, _ = _cambio({})
    estado = await cambio.atualizar()
    assert estado.taxa is None
    assert cambio.taxa() is None


async def test_nao_repete_no_mesmo_dia():
    clock = FakeClock()
    cambio, http = _cambio({URL_BCE: BCE}, clock=clock)
    await cambio.atualizar()
    clock.now += 3600
    await cambio.atualizar()
    assert http.chamadas == [URL_BCE]
    clock.now += 20 * 3600
    await cambio.atualizar()
    assert http.chamadas == [URL_BCE, URL_BCE]


async def test_manual_tem_prioridade_e_nao_e_substituido():
    cambio, http = _cambio({URL_BCE: BCE})
    cambio.definir_manual(0.006)
    estado = await cambio.atualizar(force=True)
    assert (estado.taxa, estado.manual) == (0.006, True)
    assert http.chamadas == []


async def test_voltar_auto_atualiza_ja():
    cambio, http = _cambio({URL_BCE: BCE})
    await cambio.atualizar()
    cambio.definir_manual(0.006)
    estado = await cambio.voltar_auto()
    assert (estado.taxa, estado.manual) == (0.0057, False)
    assert http.chamadas == [URL_BCE, URL_BCE]


@pytest.mark.parametrize(
    "texto, valor", [("0.0058", 0.0058), ("0,0058", 0.0058), ("abc", None), ("0", None), ("2", None), ("nan", None)]
)
def test_parse_taxa(texto, valor):
    assert parse_taxa(texto) == valor
