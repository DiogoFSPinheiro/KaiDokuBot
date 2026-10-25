from kaidokubot.rules import abaixo_do_minimo, contas

TAXA = 0.0056979


def test_contas():
    c = contas(4800, TAXA)
    assert c.montra_yen == 4800
    assert round(c.liquido_yen, 2) == 4363.64
    assert round(c.montra_eur, 2) == 27.35
    assert round(c.liquido_eur, 2) == 24.86
    assert round(c.reembolso_eur, 2) == 2.49


def test_contas_sem_taxa():
    c = contas(4800, None)
    assert (c.montra_eur, c.liquido_eur, c.reembolso_eur) == (None, None, None)
    assert round(c.liquido_yen, 2) == 4363.64


def test_abaixo_do_minimo():
    assert abaixo_do_minimo(5499) is True
    assert abaixo_do_minimo(5500) is False


# --- veredicto (fase 2) ---------------------------------------------------------------
from kaidokubot.rules import Mercado, calcular_veredicto, importar_total_eur  # noqa: E402


def _mercado(**overrides):
    campos = dict(
        termo_jp="ねんどろいど フリーレン", termo_en="nendoroid frieren 2367",
        novo_eu_eur=54.9, novo_eu_loja="JapanDco", vinted_min_eur=45.0, vinted_max_eur=65.0, vinted_n=12,
        importar_yen=6500.0, importar_loja="AmiAmi", jp_min_yen=3900.0, jp_max_yen=4500.0, jp_n=8,
        jp_so_pedidos=False, cenarios=[], razao="Razão.", fontes=[], avisos=[], vinted_tipico_eur=50.0, produto="Nendoroid Frieren 2367",
    )  # fmt: skip
    campos.update(overrides)
    return Mercado(**campos)


def test_importar_total():
    assert round(importar_total_eur(6500, TAXA), 2) == 62.51


def test_mercado_ida_e_volta_em_dict():
    m = _mercado(fontes=[{"nome": "a", "url": "u"}])
    assert Mercado.from_dict(m.to_dict()) == m


def test_compensa():
    v = calcular_veredicto(_mercado(), contas(4800, TAXA), TAXA, 20)
    assert v.codigo == "compensa"
    assert v.melhor == ("Vinted", 54.0)  # típico €50 + €4 de portes
    assert round(v.poupanca_eur, 2) == 29.14
    assert round(v.poupanca_pct) == 54
    assert v.max_montra_yen == 8300
    assert v.caro_no_japao is True


def test_pouca_diferenca():
    v = calcular_veredicto(_mercado(vinted_tipico_eur=24.0), contas(4800, TAXA), TAXA, 20)
    assert v.codigo == "pouca"
    assert round(v.poupanca_pct) == 11


def test_nao_compensa():
    v = calcular_veredicto(_mercado(vinted_tipico_eur=16.0), contas(4800, TAXA), TAXA, 20)
    assert v.codigo == "nao"
    assert round(v.poupanca_eur, 2) == -4.86


def test_melhor_e_a_alternativa_mais_barata():
    v = calcular_veredicto(_mercado(vinted_min_eur=None, vinted_max_eur=None, vinted_tipico_eur=None, novo_eu_eur=70.0), contas(4800, TAXA), TAXA, 20)
    assert v.melhor[0] == "importar (AmiAmi)"
    assert round(v.melhor[1], 2) == 62.51


def test_incerto_sem_alternativas():
    m = _mercado(novo_eu_eur=None, vinted_min_eur=None, vinted_max_eur=None, vinted_tipico_eur=None, importar_yen=None,
                 jp_min_yen=None, jp_max_yen=None, jp_n=0)  # fmt: skip
    v = calcular_veredicto(m, contas(4800, TAXA), TAXA, 20)
    assert (v.codigo, v.melhor, v.max_montra_yen) == ("incerto", None, None)
    assert "europeus" in v.motivo


def test_incerto_sem_cambio():
    v = calcular_veredicto(_mercado(jp_max_yen=None, jp_min_yen=None, jp_n=0), contas(4800, None), None, 20)
    assert v.codigo == "incerto"
    assert "câmbio" in v.motivo


def test_nao_caro_no_japao_sem_dados_ou_dentro_do_intervalo():
    assert calcular_veredicto(_mercado(jp_max_yen=None), contas(4800, TAXA), TAXA, 20).caro_no_japao is False
    assert calcular_veredicto(_mercado(jp_max_yen=5000.0), contas(4800, TAXA), TAXA, 20).caro_no_japao is False


def test_vinted_sem_tipico_usa_o_meio_do_intervalo():
    m = _mercado(vinted_tipico_eur=None, vinted_min_eur=20.0, vinted_max_eur=40.0, novo_eu_eur=None, importar_yen=None)
    assert calcular_veredicto(m, contas(4800, TAXA), TAXA, 20).melhor == ("Vinted", 34.0)


def test_cache_antiga_sem_tipico_continua_a_ler():
    dados = _mercado().to_dict()
    del dados["vinted_tipico_eur"]
    assert Mercado.from_dict(dados).vinted_tipico_eur is None


def test_caro_no_japao_exige_pelo_menos_3_comparaveis():
    assert calcular_veredicto(_mercado(jp_n=2), contas(4800, TAXA), TAXA, 20).caro_no_japao is False
    assert calcular_veredicto(_mercado(jp_n=3), contas(4800, TAXA), TAXA, 20).caro_no_japao is True


def test_vinted_com_um_so_anuncio_nao_entra_no_veredicto():
    m = _mercado(vinted_n=1, novo_eu_eur=None, importar_yen=None, jp_n=1)
    v = calcular_veredicto(m, contas(4800, TAXA), TAXA, 20)
    assert (v.codigo, v.motivo) == ("incerto", "sem preços europeus fiáveis")



def _sem_europa(**overrides):
    campos = dict(novo_eu_eur=None, vinted_min_eur=None, vinted_max_eur=None, vinted_tipico_eur=None, importar_yen=None)
    campos.update(overrides)
    return _mercado(**campos)


import pytest  # noqa: E402


@pytest.mark.parametrize("preco, codigo", [(3500, "jp_bom"), (4200, "jp_normal"), (4800, "jp_caro")])
def test_sem_europa_compara_com_o_mercari(preco, codigo):
    v = calcular_veredicto(_sem_europa(), contas(preco, TAXA), TAXA, 20)
    assert v.codigo == codigo
    assert v.max_montra_yen == 4500  # o topo dos vendidos no Mercari
    assert v.caro_no_japao is False  # o próprio veredicto já o diz


def test_sem_europa_e_um_so_vendido_continua_incerto():
    v = calcular_veredicto(_sem_europa(jp_n=1), contas(4800, TAXA), TAXA, 20)
    assert v.codigo == "incerto"


def test_sem_europa_sem_cambio_compara_com_o_mercari_na_mesma():
    assert calcular_veredicto(_sem_europa(), contas(4800, None), None, 20).codigo == "jp_caro"
