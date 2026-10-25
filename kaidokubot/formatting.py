from __future__ import annotations

from html import escape

from kaidokubot.parsing import Pedido
from kaidokubot.rules import IMPOSTO, MINIMO_SEM_IMPOSTO, Contas, abaixo_do_minimo

HELP = (
    "Olá! Diz-me o artigo e o preço e eu faço as contas.\n\n"
    "Exemplos:\n"
    "• nendoroid frieren 4800\n"
    "• zelda totk ¥3,980 sem caixa\n"
    "• 4.800円 pop up parade fern selado\n\n"
    "O preço é o número com ¥/円/yen ou, se não houver, o último número. "
    "Estados: selado, novo, usado, sem caixa, caixa danificada (também em inglês e japonês: 未開封, 中古, 箱なし, 箱傷み…).\n\n"
    "/cambio – ver o câmbio ¥→€ (/cambio 0.0058 fixa um valor, /cambio auto volta ao automático)\n"
    "/id – mostrar o chat id"
)


def fmt_yen(valor: float) -> str:
    return "¥" + f"{round(valor):,}".replace(",", ".")


def fmt_eur(valor: float) -> str:
    return f"€{valor:.2f}"


def linha_contas(c: Contas) -> str:
    if c.montra_eur is None or c.liquido_eur is None or c.reembolso_eur is None:
        return f"{fmt_yen(c.montra_yen)} → €? (câmbio indisponível)"
    return (
        f"{fmt_yen(c.montra_yen)} → {fmt_eur(c.montra_eur)} em loja · "
        f"{fmt_eur(c.liquido_eur)} após reembolso (+{fmt_eur(c.reembolso_eur)})"
    )


def resposta_imediata(p: Pedido, c: Contas) -> str:
    lines = [f"📦 <b>{escape(p.nome)}</b>", escape(linha_contas(c)), f"Estado: {escape(p.estado)}"]
    if abaixo_do_minimo(p.preco_yen):
        minimo = fmt_yen(MINIMO_SEM_IMPOSTO * (1 + IMPOSTO))
        lines.append(f"ℹ️ reembolso só se somares ≥ {minimo} nesta loja hoje")
    return "\n".join(lines)
