from kaidokubot.formatting import fmt_eur, fmt_yen, linha_contas, resposta_imediata
from kaidokubot.parsing import Pedido
from kaidokubot.rules import contas

TAXA = 0.0056979


def test_linha_contas():
    assert linha_contas(contas(4800, TAXA)) == "¥4.800 → €27.35 em loja · €24.86 após reembolso (+€2.49)"


def test_linha_contas_sem_cambio():
    assert linha_contas(contas(4800, None)) == "¥4.800 → €? (câmbio indisponível)"


def test_fmt_yen_milhares():
    assert fmt_yen(1234567) == "¥1.234.567"
    assert fmt_yen(4363.64) == "¥4.364"
    assert fmt_yen(980) == "¥980"


def test_fmt_eur():
    assert fmt_eur(27.349) == "€27.35"
    assert fmt_eur(1234.5) == "€1234.50"


def test_resposta_imediata():
    texto = resposta_imediata(Pedido("Nendoroid <Frieren>", 4800, "caixa danificada"), contas(4800, TAXA))
    assert texto.splitlines() == [
        "📦 <b>Nendoroid &lt;Frieren&gt;</b>",
        "¥4.800 → €27.35 em loja · €24.86 após reembolso (+€2.49)",
        "Estado: caixa danificada",
        "ℹ️ reembolso só se somares ≥ ¥5.500 nesta loja hoje",
    ]


def test_resposta_imediata_sem_nota_acima_do_minimo():
    texto = resposta_imediata(Pedido("PS5", 6000, "usado"), contas(6000, TAXA))
    assert "ℹ️" not in texto
    assert texto.splitlines()[-1] == "Estado: usado"


# --- resultado da avaliação (fase 2) ---------------------------------------------------
from kaidokubot.formatting import resultado, resumo  # noqa: E402
from kaidokubot.rules import calcular_veredicto  # noqa: E402
from tests.test_rules import _mercado  # noqa: E402

PEDIDO = Pedido("nendoroid frieren", 4800, "selado")


def _resultado(m, criado_em=None, agora=1_000_000.0, taxa=TAXA):
    c = contas(4800, taxa)
    return resultado(PEDIDO, c, m, calcular_veredicto(m, c, taxa, 20), criado_em, agora)


def test_resultado_completo():
    m = _mercado(fontes=[{"nome": "JapanDco", "url": "https://j.example/x"}, {"nome": "Vinted <pt>", "url": "https://v"}])
    assert _resultado(m).splitlines() == [
        "📦 <b>nendoroid frieren</b> · ¥4.800 → €24.86 após reembolso",
        "🔍 Nendoroid 2367 Frieren",
        "🟢 <b>Compensa</b> — poupas €29.14 (54%) face a Vinted (€54.00)",
        "💴 Pagaria no máximo ¥8.300",
        "🇪🇺 Novo €54.90 (JapanDco) · Vinted ~€50.00 + portes (€45.00–65.00, 12) · importar ~€62.51 (AmiAmi)",
        "🇯🇵 Mercari vendidos ¥3.900–4.500 (8)",
        "👀 Acima do normal no Japão — vê noutras lojas",
        "Razão.",
        '🔗 <a href="https://j.example/x">JapanDco</a> · <a href="https://v">Vinted &lt;pt&gt;</a>',
    ]


def test_resultado_nao_compensa_e_so_pedidos():
    m = _mercado(vinted_min_eur=16.0, vinted_max_eur=None, vinted_tipico_eur=16.0, novo_eu_eur=None, importar_yen=None,
                 jp_so_pedidos=True, jp_max_yen=6000.0, avisos=["Vinted indisponível"])  # fmt: skip
    linhas = _resultado(m).splitlines()
    assert linhas[2] == "🔴 <b>Não compensa</b> — €4.86 mais caro que Vinted (€20.00)"
    assert "🇪🇺 Vinted ~€16.00 + portes (12)" in linhas
    assert "🇯🇵 Mercari à venda ¥3.900–6.000 (só anúncios, sem vendas)" in linhas
    assert "⚠️ Vinted indisponível" in linhas


def test_resultado_incerto():
    m = _mercado(novo_eu_eur=None, vinted_min_eur=None, vinted_max_eur=None, vinted_tipico_eur=None, vinted_n=0,
                 importar_yen=None,
                 jp_min_yen=None, jp_max_yen=None, jp_n=0)  # fmt: skip
    linhas = _resultado(m).splitlines()
    assert linhas[2] == "⚪ <b>Incerto</b> — sem preços europeus fiáveis"
    assert not any(l.startswith(("💴", "🇪🇺", "🇯🇵")) for l in linhas)


def test_resultado_cenarios_com_estado_desconhecido():
    m = _mercado(cenarios=[{"estado": "selado", "eu_min": 50, "eu_max": 60, "jp_min": 5000, "jp_max": 6000},
                           {"estado": "usado", "eu_min": None, "eu_max": None, "jp_min": 3000, "jp_max": 4000}])  # fmt: skip
    linhas = _resultado(m).splitlines()
    assert "• selado: 🇪🇺 €50.00–60.00 · 🇯🇵 ¥5.000–6.000" in linhas
    assert "• usado: 🇯🇵 ¥3.000–4.000" in linhas


def test_resultado_da_cache():
    agora = 1_000_000.0
    assert _resultado(_mercado(), criado_em=agora - 4 * 86400 - 60, agora=agora).splitlines()[-1] == "🕒 avaliado há 4 dias"
    assert _resultado(_mercado(), criado_em=agora - 3 * 3600, agora=agora).splitlines()[-1] == "🕒 avaliado há 3 h"
    assert _resultado(_mercado(), criado_em=agora - 120, agora=agora).splitlines()[-1] == "🕒 avaliado há 2 min"


def test_nome_da_loja_longo_e_cortado():
    m = _mercado(novo_eu_loja="Amazon (promoção reportada em junho de 2026; PVP €69,99)", importar_yen=None,
                 vinted_min_eur=None, vinted_max_eur=None, vinted_tipico_eur=None)  # fmt: skip
    linha = next(l for l in _resultado(m).splitlines() if l.startswith("🇪🇺"))
    assert linha == "🇪🇺 Novo €54.90 (Amazon)"



# --- resumo compacto ----------------------------------------------------------------
def _resumo(m, criado_em=None, agora=1_000_000.0, taxa=TAXA, preco=4800, estado="selado"):
    c = contas(preco, taxa)
    return resumo(c, m, calcular_veredicto(m, c, taxa, 20), criado_em, agora, estado=estado)


def test_resumo_compacto():
    assert _resumo(_mercado()).splitlines() == [
        "🟢 <b>Compensa</b> · poupas €29 (54%)",
        "💴 Máximo ¥8.300",
        "🇪🇺 Vinted ~€50 (12) · novo €55 (JapanDco) · importar ~€63",
        "🇯🇵 Mercari ¥3.900–4.500 (8) · 👀 caro aqui",
        "🔍 Nendoroid 2367 Frieren",
    ]


def test_resumo_estado_desconhecido_avisa():
    assert "❔ Sem estado: comparei como usado (✏️ Corrigir para afinar)" in _resumo(_mercado(), estado="desconhecido").splitlines()


def test_resumo_nao_compensa_sem_japao_com_avisos_e_cache():
    m = _mercado(vinted_tipico_eur=16.0, novo_eu_eur=None, importar_yen=None, jp_min_yen=None, jp_max_yen=None,
                 avisos=["Mercari indisponível"], produto="")  # fmt: skip
    assert _resumo(m, criado_em=1_000_000.0 - 2 * 86400).splitlines() == [
        "🔴 <b>Não compensa</b> · €5 mais caro que na Europa",
        "💴 Máximo ¥3.000",
        "🇪🇺 Vinted ~€16 (12)",
        "⚠️ Mercari indisponível",
        "🕒 avaliado há 2 dias",
    ]


def test_resumo_incerto_e_so_pedidos():
    m = _mercado(novo_eu_eur=None, vinted_min_eur=None, vinted_max_eur=None, vinted_tipico_eur=None,
                 importar_yen=None, jp_so_pedidos=True, jp_max_yen=4900.0, produto="")  # fmt: skip
    assert _resumo(m).splitlines() == [
        "⚪ <b>Incerto</b> · sem preços europeus fiáveis",
        "🇯🇵 Mercari à venda ¥3.900–4.900 (8)",
    ]


def test_resumo_mostra_quantos_anuncios_da_vinted():
    m = _mercado(vinted_n=1, novo_eu_eur=None, importar_yen=None, produto="")
    assert "🇪🇺 Vinted ~€50 (1)" in _resumo(m).splitlines()
