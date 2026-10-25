import asyncio

import pytest

from kaidokubot.appraisal import Avaliador
from kaidokubot.claude import ClaudeError
from kaidokubot.fontes import Anuncio, FonteError
from kaidokubot.fx import Cambio
from kaidokubot.parsing import Pedido
from kaidokubot.storage import Storage
from tests.fakes import FakeClock, FakeHttp, FakeMercari, FakeRunner, FakeVinted

TAXA = 0.0056979
TERMOS = {"termo_jp": "ねんどろいど フリーレン", "termo_en": "nendoroid frieren"}
MERCADO = {
    "novo_eu_eur": 54.9, "novo_eu_loja": "JapanDco", "vinted_min_eur": 45.0, "vinted_max_eur": 65.0, "vinted_n": 3,
    "importar_yen": 6500, "importar_loja": "AmiAmi", "jp_min_yen": 3900, "jp_max_yen": 4500, "jp_n": 8,
    "jp_so_pedidos": False, "cenarios": [], "razao": "Vendas no Mercari e anúncios na Vinted.",
    "fontes": [{"nome": "JapanDco", "url": "https://japandco.net/x"}],
}  # fmt: skip


def _avaliador(storage, runner=None, mercari=None, vinted=None, max_dia=30, clock=None):
    cambio = Cambio(storage, FakeHttp(), now=FakeClock())
    cambio.definir_manual(TAXA)
    return Avaliador(
        storage, cambio, runner or FakeRunner({"termos": TERMOS, "mercado": MERCADO}, pesquisas=["q1"]),
        mercari or FakeMercari([Anuncio("ねんどろいど フリーレン 2367", 4200, "novo")], [Anuncio("x", 6800, "novo")]),
        vinted or FakeVinted([Anuncio("Nendoroid Frieren 2367", 63.7, "Novo com etiquetas")]),
        max_dia=max_dia, margem=20, cache_dias=30, now=clock or FakeClock(),
    )  # fmt: skip


@pytest.fixture
def storage():
    s = Storage()
    s.add_pedido(1, Pedido("nendoroid frieren", 4800, "selado"))
    return s


async def test_avaliacao_completa(storage):
    runner = FakeRunner({"termos": TERMOS, "mercado": MERCADO}, pesquisas=["nendoroid frieren prix"])
    mercari = FakeMercari([Anuncio("ねんどろいど フリーレン 2367", 4200, "novo")])
    vinted = FakeVinted([Anuncio("Nendoroid Frieren 2367", 63.7, "Novo com etiquetas")])
    progresso = []
    r = await _avaliador(storage, runner, mercari, vinted).avaliar(1, 1, False, progresso.append)
    assert r.texto.splitlines()[0].startswith("🟢 <b>Compensa</b>")
    assert r.botoes == [[("📋 Detalhes", "det:1"), ("🔄 Reavaliar", "rv:1"), ("✏️ Corrigir", "fix:1")]]
    assert (mercari.termos, vinted.termos) == (["ねんどろいど フリーレン"], ["nendoroid frieren"])
    assert [tipo for tipo, _, _ in runner.chamadas] == ["termos", "mercado"]
    _, prompt, tools = runner.chamadas[1]
    assert tools == "WebSearch"
    assert "ねんどろいど フリーレン 2367 | ¥4.200 | novo" in prompt
    assert "Nendoroid Frieren 2367 | €63.70 | Novo com etiquetas" in prompt
    assert "¥4.800" in prompt and "selado" in prompt
    assert any(p.startswith("🔎 Mercari: 1 vendidos") for p in progresso)
    assert any("🌐 A pesquisar: nendoroid frieren prix" in p for p in progresso)
    assert storage.contar_avaliacoes(0) == 1


async def test_fontes_do_mercari_e_vinted_acrescentadas(storage):
    avaliador = _avaliador(storage)
    await avaliador.avaliar(1, 1, False, lambda _: None)
    r = avaliador.mostrar(1, detalhes=True)
    assert "jp.mercari.com/search?keyword=" in r.texto
    assert "www.vinted.pt/catalog?search_text=nendoroid+frieren" in r.texto


async def test_segunda_vez_usa_cache_com_o_preco_atual(storage):
    clock = FakeClock()
    runner = FakeRunner({"termos": TERMOS, "mercado": MERCADO})
    avaliador = _avaliador(storage, runner, clock=clock)
    await avaliador.avaliar(1, 1, False, lambda _: None)
    storage.add_pedido(1, Pedido("Nendoroid  Frieren", 9000, "selado"))
    clock.now += 2 * 86400
    r = await avaliador.avaliar(1, 2, False, lambda _: None)
    assert len(runner.chamadas) == 2  # só a primeira avaliação chamou o Claude
    assert r.texto.startswith("🟡 <b>Pouca diferença</b>")  # recalculado para ¥9.000 (era 🟢 a ¥4.800)
    assert r.texto.splitlines()[-1] == "🕒 avaliado há 2 dias"
    assert storage.contar_avaliacoes(0) == 1


async def test_cache_expira(storage):
    clock = FakeClock()
    runner = FakeRunner({"termos": TERMOS, "mercado": MERCADO})
    avaliador = _avaliador(storage, runner, clock=clock)
    await avaliador.avaliar(1, 1, False, lambda _: None)
    clock.now += 31 * 86400
    await avaliador.avaliar(1, 1, False, lambda _: None)
    assert len(runner.chamadas) == 4


async def test_forcar_ignora_cache(storage):
    runner = FakeRunner({"termos": TERMOS, "mercado": MERCADO})
    avaliador = _avaliador(storage, runner)
    await avaliador.avaliar(1, 1, False, lambda _: None)
    r = await avaliador.avaliar(1, 1, True, lambda _: None)
    assert len(runner.chamadas) == 4
    assert "🕒" not in r.texto


async def test_limite_diario(storage):
    storage.add_pedido(1, Pedido("zelda totk", 3980, "usado"))
    avaliador = _avaliador(storage, max_dia=1)
    await avaliador.avaliar(1, 1, False, lambda _: None)
    r = await avaliador.avaliar(1, 2, False, lambda _: None)
    assert "limite de 1 avaliação" in r.texto
    # A cache continua a funcionar acima do limite.
    assert "🕒" in (await avaliador.avaliar(1, 1, False, lambda _: None)).texto


async def test_fontes_em_baixo_continua_e_avisa(storage):
    avaliador = _avaliador(
        storage, mercari=FakeMercari(erro=FonteError("Mercari: timeout")), vinted=FakeVinted(erro=FonteError("x"))
    )
    r = await avaliador.avaliar(1, 1, False, lambda _: None)
    assert "⚠️ Mercari indisponível" in r.texto
    assert "⚠️ Vinted indisponível" in r.texto
    assert "🟢" in r.texto


@pytest.mark.parametrize("tipo", ["termos", "mercado"])
async def test_claude_falha_nao_conta_nem_guarda(storage, tipo):
    respostas = {"termos": TERMOS, "mercado": MERCADO, tipo: ClaudeError("o Claude demorou demasiado")}
    r = await _avaliador(storage, FakeRunner(respostas)).avaliar(1, 1, False, lambda _: None)
    assert r.texto == "❌ Não consegui avaliar: o Claude demorou demasiado"
    assert r.botoes == [[("💡 Tentar outra vez", "av:1")]]
    assert storage.contar_avaliacoes(0) == 0


async def test_resposta_incompleta_do_claude(storage):
    runner = FakeRunner({"termos": TERMOS, "mercado": {"razao": "x"}})
    r = await _avaliador(storage, runner).avaliar(1, 1, False, lambda _: None)
    assert r.texto.startswith("❌ Não consegui avaliar")
    assert storage.contar_avaliacoes(0) == 0


async def test_fila_e_cache_partilhada(storage):
    bloquear = asyncio.Event()
    runner = FakeRunner({"termos": TERMOS, "mercado": MERCADO}, bloquear=bloquear)
    avaliador = _avaliador(storage, runner)
    p1, p2 = [], []
    t1 = asyncio.create_task(avaliador.avaliar(1, 1, False, p1.append))
    await asyncio.sleep(0.01)
    t2 = asyncio.create_task(avaliador.avaliar(1, 1, False, p2.append))
    await asyncio.sleep(0.01)
    assert p2 == ["⏳ Na fila (posição 1)…"]
    bloquear.set()
    r1, r2 = await asyncio.gather(t1, t2)
    assert "🕒" not in r1.texto and "🕒" in r2.texto
    assert [tipo for tipo, _, _ in runner.chamadas] == ["termos", "mercado"]


async def test_pedido_inexistente(storage):
    r = await _avaliador(storage).avaliar(1, 99, False, lambda _: None)
    assert r.texto.startswith("Já não tenho esse pedido")


async def test_detalhes_e_resumo(storage):
    clock = FakeClock()
    avaliador = _avaliador(storage, clock=clock)
    resumo_r = await avaliador.avaliar(1, 1, False, lambda _: None)
    clock.now += 3 * 3600
    det = avaliador.mostrar(1, detalhes=True)
    assert det.texto.startswith("📦 <b>nendoroid frieren</b>")
    assert "Vendas no Mercari e anúncios na Vinted." in det.texto
    assert det.botoes[0][0] == ("📌 Resumo", "res:1")
    assert det.texto.splitlines()[-1] == "🕒 avaliado há 3 h"
    assert avaliador.mostrar(1, detalhes=False).texto.splitlines()[:4] == resumo_r.texto.splitlines()[:4]
    assert avaliador.mostrar(99, detalhes=True).texto.startswith("Já não tenho")


async def test_cache_guarda_quando_os_dados_foram_recolhidos(storage):
    clock = FakeClock()
    avaliador = _avaliador(storage, clock=clock)
    await avaliador.avaliar(1, 1, False, lambda _: None)
    clock.now += 2 * 86400
    await avaliador.avaliar(1, 1, False, lambda _: None)  # da cache -> avaliação 2
    clock.now += 86400
    assert avaliador.mostrar(2, detalhes=False).texto.splitlines()[-1] == "🕒 avaliado há 3 dias"
