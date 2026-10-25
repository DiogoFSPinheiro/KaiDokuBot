from __future__ import annotations

from html import escape

from kaidokubot.fx import EstadoCambio
from kaidokubot.parsing import Pedido
from kaidokubot.rules import (
    IMPOSTO, MINIMO_SEM_IMPOSTO, Contas, Mercado, Veredicto, abaixo_do_minimo, importar_total_eur,
    loja_curta,
)  # fmt: skip

HELP = (
    "Olá! Diz-me o artigo e o preço e eu faço as contas.\n\n"
    "Exemplos:\n"
    "• nendoroid frieren 4800\n"
    "• zelda totk ¥3,980 sem caixa\n"
    "• 4.800円 pop up parade fern selado\n\n"
    "O preço é o número com ¥/円/yen ou, se não houver, o último número. "
    "Estados: selado, novo, usado, sem caixa, caixa danificada (também em inglês e japonês: 未開封, 中古, 箱なし, 箱傷み…).\n\n"
    "💡 Avaliar compara com o preço na Europa (lojas, Vinted, importar) e com o Mercari japonês; demora 1–4 min.\n\n"
    "/cambio – ver o câmbio ¥→€ (/cambio 0.0058 fixa um valor, /cambio auto volta ao automático)\n"
    "/id – mostrar o chat id"
)


def fmt_yen(valor: float) -> str:
    return "¥" + f"{round(valor):,}".replace(",", ".")


def fmt_eur(valor: float) -> str:
    return f"€{valor:.2f}"


def _intervalo(lo: float | None, hi: float | None, fmt) -> str | None:
    if lo is None and hi is None:
        return None
    if lo is None or hi is None or round(lo, 2) == round(hi, 2):
        return fmt(lo if lo is not None else hi)
    return f"{fmt(lo)}–{fmt(hi).lstrip('€¥')}"


def linha_contas(c: Contas) -> str:
    if c.montra_eur is None or c.liquido_eur is None or c.reembolso_eur is None:
        return f"{fmt_yen(c.montra_yen)} → €? (câmbio indisponível)"
    return (
        f"{fmt_yen(c.montra_yen)} → {fmt_eur(c.montra_eur)} em loja · "
        f"{fmt_eur(c.liquido_eur)} após reembolso (+{fmt_eur(c.reembolso_eur)})"
    )


def texto_cambio(e: EstadoCambio) -> str:
    if e.taxa is None:
        return "💱 Câmbio indisponível (ainda não consegui obtê-lo). Fixa um valor com /cambio 0.0058"
    origem = "manual" if e.manual else f"{e.fonte}, {e.data}"
    taxa = f"{e.taxa:.7f}".rstrip("0")
    return f"💱 1 ¥ = €{taxa} ({origem})\n{fmt_yen(1000)} = {fmt_eur(1000 * e.taxa)}"


def resposta_imediata(p: Pedido, c: Contas) -> str:
    lines = [f"📦 <b>{escape(p.nome)}</b>", escape(linha_contas(c)), f"Estado: {escape(p.estado)}"]
    if abaixo_do_minimo(p.preco_yen):
        minimo = fmt_yen(MINIMO_SEM_IMPOSTO * (1 + IMPOSTO))
        lines.append(f"ℹ️ reembolso só se somares ≥ {minimo} nesta loja hoje")
    return "\n".join(lines)


MAX_RAZAO = 600
MAX_FONTES = 8
_CABECALHO = {"compensa": "🟢 <b>Compensa</b>", "pouca": "🟡 <b>Pouca diferença</b>",
              "nao": "🔴 <b>Não compensa</b>", "incerto": "⚪ <b>Incerto</b>"}  # fmt: skip


def _ha_quanto(segundos: float) -> str:
    if segundos < 3600:
        return f"há {max(1, int(segundos // 60))} min"
    if segundos < 86400:
        return f"há {int(segundos // 3600)} h"
    dias = int(segundos // 86400)
    return f"há {dias} {'dia' if dias == 1 else 'dias'}"


def _linha_veredicto(v: Veredicto) -> str:
    cabecalho = _CABECALHO[v.codigo]
    if v.codigo == "incerto" or v.melhor is None or v.poupanca_eur is None:
        return f"{cabecalho} — {escape(v.motivo or '')}"
    rotulo = f"{escape(v.melhor[0])} ({fmt_eur(v.melhor[1])})"
    if v.codigo == "nao":
        return f"{cabecalho} — {fmt_eur(-v.poupanca_eur)} mais caro que {rotulo}"
    return f"{cabecalho} — poupas {fmt_eur(v.poupanca_eur)} ({round(v.poupanca_pct)}%) face a {rotulo}"


def _linha_europa(m: Mercado, taxa: float | None) -> str | None:
    partes = []
    if m.novo_eu_eur:
        loja = f" ({escape(loja_curta(m.novo_eu_loja))})" if loja_curta(m.novo_eu_loja) else ""
        partes.append(f"Novo {fmt_eur(m.novo_eu_eur)}{loja}")
    if m.vinted_eur:
        intervalo = _intervalo(m.vinted_min_eur, m.vinted_max_eur, fmt_eur)
        detalhe = f"{intervalo}, {m.vinted_n}" if intervalo and "–" in intervalo else str(m.vinted_n)
        partes.append(f"Vinted ~{fmt_eur(m.vinted_eur)} + portes ({detalhe})")
    if m.importar_yen and taxa is not None:
        loja = f" ({escape(loja_curta(m.importar_loja))})" if loja_curta(m.importar_loja) else ""
        partes.append(f"importar ~{fmt_eur(importar_total_eur(m.importar_yen, taxa))}{loja}")
    return "🇪🇺 " + " · ".join(partes) if partes else None


def _linha_japao(m: Mercado) -> str | None:
    jp = _intervalo(m.jp_min_yen, m.jp_max_yen, fmt_yen)
    if not jp:
        return None
    if m.jp_so_pedidos:
        return f"🇯🇵 Mercari à venda {jp} (só anúncios, sem vendas)"
    return f"🇯🇵 Mercari vendidos {jp} ({m.jp_n})"


def _linha_cenario(cenario: dict) -> str:
    partes = []
    eu = _intervalo(cenario.get("eu_min"), cenario.get("eu_max"), fmt_eur)
    if eu:
        partes.append(f"🇪🇺 {eu}")
    jp = _intervalo(cenario.get("jp_min"), cenario.get("jp_max"), fmt_yen)
    if jp:
        partes.append(f"🇯🇵 {jp}")
    return f"• {escape(str(cenario.get('estado', '?')))}: " + (" · ".join(partes) or "sem dados")


def resultado(p: Pedido, c: Contas, m: Mercado, v: Veredicto, criado_em: float | None, agora: float) -> str:
    """Resultado da avaliação (HTML). criado_em != None quando vem da cache."""
    taxa = c.montra_eur / c.montra_yen if c.montra_eur is not None else None
    liquido = f" → {fmt_eur(c.liquido_eur)} após reembolso" if c.liquido_eur is not None else ""
    lines = [f"📦 <b>{escape(p.nome)}</b> · {fmt_yen(c.montra_yen)}{liquido}"]
    if m.produto:
        lines.append(f"🔍 {escape(m.produto)}")
    lines.append(_linha_veredicto(v))
    if v.max_montra_yen and v.max_montra_yen > 0:
        lines.append(f"💴 Pagaria no máximo {fmt_yen(v.max_montra_yen)}")
    lines += [linha for linha in (_linha_europa(m, taxa), _linha_japao(m)) if linha]
    lines += [_linha_cenario(cenario) for cenario in m.cenarios]
    if v.caro_no_japao:
        lines.append("👀 Acima do normal no Japão — vê noutras lojas")
    lines += [f"⚠️ {escape(aviso)}" for aviso in m.avisos]
    if m.razao:
        razao = m.razao if len(m.razao) <= MAX_RAZAO else m.razao[: MAX_RAZAO - 1] + "…"
        lines.append(escape(razao))
    links = [
        f'<a href="{escape(f["url"], quote=True)}">{escape(f["nome"])}</a>'
        for f in m.fontes[:MAX_FONTES]
        if f.get("url", "").startswith("http")
    ]
    if links:
        lines.append("🔗 " + " · ".join(links))
    if criado_em is not None:
        lines.append(f"🕒 avaliado {_ha_quanto(agora - criado_em)}")
    return "\n".join(lines)


def _link(texto: str, url: str) -> str:
    """Texto (já em HTML) com link, se o URL for http(s); senão só o texto."""
    if not url.startswith(("https://", "http://")):
        return texto
    return f'<a href="{escape(url, quote=True)}">{texto}</a>'


def _eur0(valor: float) -> str:
    return f"€{round(valor)}"


_CURTO = {"compensa": "🟢 <b>Compensa</b>", "pouca": "🟡 <b>Pouca diferença</b>",
          "nao": "🔴 <b>Não compensa</b>", "incerto": "⚪ <b>Incerto</b>"}  # fmt: skip


def resumo(
    c: Contas, m: Mercado, v: Veredicto, criado_em: float | None, agora: float, *, estado: str = "desconhecido"
) -> str:
    """Resultado compacto para ler de pé na loja (o artigo já aparece citado por cima)."""
    taxa = c.montra_eur / c.montra_yen if c.montra_eur is not None else None
    cabecalho = _CURTO[v.codigo]
    if v.codigo == "incerto" or v.poupanca_eur is None:
        lines = [f"{cabecalho} · {escape(v.motivo or '')}"]
    elif v.codigo == "nao":
        lines = [f"{cabecalho} · {_eur0(-v.poupanca_eur)} mais caro que na Europa"]
    else:
        lines = [f"{cabecalho} · poupas {_eur0(v.poupanca_eur)} ({round(v.poupanca_pct)}%)"]
    if v.max_montra_yen and v.max_montra_yen > 0:
        lines.append(f"💴 Máximo {fmt_yen(v.max_montra_yen)}")
    europa = []
    if m.vinted_eur:
        europa.append(_link(f"Vinted ~{_eur0(m.vinted_eur)} ({m.vinted_n})", m.vinted_url))
    if m.novo_eu_eur:
        loja = loja_curta(m.novo_eu_loja)
        europa.append(_link(f"novo {_eur0(m.novo_eu_eur)}" + (f" ({escape(loja)})" if loja else ""), m.novo_eu_url))
    if m.importar_yen and taxa is not None:
        europa.append(_link(f"importar ~{_eur0(importar_total_eur(m.importar_yen, taxa))}", m.importar_url))
    if europa:
        lines.append("🇪🇺 " + " · ".join(europa))
    jp = _intervalo(m.jp_min_yen, m.jp_max_yen, fmt_yen)
    if jp:
        linha = _link(f"Mercari {'à venda ' if m.jp_so_pedidos else ''}{jp} ({m.jp_n})", m.mercari_url)
        lines.append(f"🇯🇵 {linha}" + (" · 👀 caro aqui" if v.caro_no_japao else ""))
    if m.produto:
        lines.append(f"🔍 {_link(escape(m.produto), m.produto_url)}")
    if estado == "desconhecido":
        lines.append("❔ Sem estado: comparei como usado (✏️ Corrigir para afinar)")
    lines += [f"⚠️ {escape(aviso)}" for aviso in m.avisos]
    if criado_em is not None:
        lines.append(f"🕒 avaliado {_ha_quanto(agora - criado_em)}")
    return "\n".join(lines)
