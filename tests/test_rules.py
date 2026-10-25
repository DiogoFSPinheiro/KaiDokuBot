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
