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
