from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from kaidokubot.fx import EstadoCambio
from kaidokubot.parsing import Pedido
from kaidokubot.rules import (
    IMPOSTO, MINIMO_SEM_IMPOSTO, Contas, Mercado, Veredicto, abaixo_do_minimo, importar_total_eur,
    loja_curta,
)  # fmt: skip

TOKYO = ZoneInfo("Asia/Tokyo")

HELP = (
    "Olá! Diz-me o artigo e o preço e eu faço as contas.\n\n"
    "Exemplos:\n"
    "• nendoroid frieren 4800\n"
    "• zelda totk ¥3,980 sem caixa\n"
    "• 4.800円 pop up parade fern selado\n\n"
    "O preço é o número com ¥/円/yen ou, se não houver, o último número. "
    "Estados: selado, novo, usado, sem caixa, caixa danificada (também em inglês e japonês: 未開封, 中古, 箱なし, 箱傷み…).\n\n"
    "📷 Também podes mandar uma foto da etiqueta ou da caixa (com o preço na legenda, se quiseres).\n\n"
    "Cada pedido é avaliado logo: compara com o preço na Europa (lojas, Vinted, importar) e com o Mercari "
    "japonês; demora ~30 s.\n"
    "Em Portugal, põe o preço em euros (ex.: nendoroid frieren 35€): compara só com a Europa.\n\n"
    "/historico – últimas 10 avaliações\n"
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
    if p.em_euros:
        return f"📦 <b>{escape(p.nome)}</b> · {fmt_eur(p.preco_eur)}\nEstado: {escape(p.estado)}"
    lines = [f"📦 <b>{escape(p.nome)}</b>", escape(linha_contas(c)), f"Estado: {escape(p.estado)}"]
    if abaixo_do_minimo(p.preco_yen):
        minimo = fmt_yen(MINIMO_SEM_IMPOSTO * (1 + IMPOSTO))
        lines.append(f"ℹ️ reembolso só se somares ≥ {minimo} nesta loja hoje")
    return "\n".join(lines)


MAX_RAZAO = 600
MAX_FONTES = 8
_CABECALHO = {"compensa": "🟢 <b>Compensa</b>", "pouca": "🟡 <b>Pouca diferença</b>",
              "nao": "🔴 <b>Não compensa</b>", "incerto": "⚪ <b>Incerto</b>",
              "jp_bom": "🟢 <b>Bom preço para o Japão</b>", "jp_normal": "🟡 <b>Preço normal no Japão</b>",
              "jp_caro": "🔴 <b>Caro para o Japão</b>",
              "eu_bom": "🟢 <b>Bom preço</b>", "eu_normal": "🟡 <b>Preço normal</b>", "eu_caro": "🔴 <b>Caro</b>"}  # fmt: skip


def _ha_quanto(segundos: float) -> str:
    if segundos < 3600:
        return f"há {max(1, int(segundos // 60))} min"
    if segundos < 86400:
        return f"há {int(segundos // 3600)} h"
    dias = int(segundos // 86400)
    return f"há {dias} {'dia' if dias == 1 else 'dias'}"


def _linha_veredicto(v: Veredicto) -> str:
    cabecalho = _CABECALHO[v.codigo]
    if v.codigo.startswith("eu_"):
        return _linha_veredicto_eur(v)
    if v.codigo.startswith("jp_"):
        return f"{cabecalho} — sem preços europeus; comparado com os vendidos no Mercari"
    if v.codigo == "incerto" or v.melhor is None or v.poupanca_eur is None:
        return f"{cabecalho} — {escape(v.motivo or '')}"
    rotulo = f"{escape(v.melhor[0])} ({fmt_eur(v.melhor[1])})"
    if v.codigo == "nao":
        return f"{cabecalho} — {fmt_eur(-v.poupanca_eur)} mais caro que {rotulo}"
    return f"{cabecalho} — poupas {fmt_eur(v.poupanca_eur)} ({round(v.poupanca_pct)}%) face a {rotulo}"


def _linha_veredicto_eur(v: Veredicto) -> str:
    diferenca = abs(v.poupanca_eur)
    lado = "abaixo" if v.poupanca_eur >= 0 else "acima"
    return f"{_CABECALHO[v.codigo]} · {_eur0(diferenca)} {lado} da Europa ({round(abs(v.poupanca_pct))}%)"


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


def _mercari_em_eur(m: Mercado, taxa: float | None) -> str:
    """« ≈ €22–26» ao lado do intervalo em ienes (vazio sem câmbio)."""
    if taxa is None or not (m.jp_min_yen or m.jp_max_yen):
        return ""
    lo = m.jp_min_yen * taxa if m.jp_min_yen else None
    hi = m.jp_max_yen * taxa if m.jp_max_yen else None
    return f" ≈ {_intervalo(lo, hi, _eur0)}"


def _linha_japao(m: Mercado, taxa: float | None) -> str | None:
    jp = _intervalo(m.jp_min_yen, m.jp_max_yen, fmt_yen)
    if not jp:
        return None
    eur = _mercari_em_eur(m, taxa)
    if m.jp_so_pedidos:
        return f"🇯🇵 Mercari à venda {jp}{eur} (só anúncios, sem vendas)"
    return f"🇯🇵 Mercari vendidos {jp}{eur} ({m.jp_n})"


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
    if p.em_euros:
        taxa = None  # modo Europa: sem importação nem Japão
        lines = [f"📦 <b>{escape(p.nome)}</b> · {fmt_eur(p.preco_eur)}"]
    else:
        lines = [f"📦 <b>{escape(p.nome)}</b> · {fmt_yen(c.montra_yen)}{liquido}"]
    if m.produto:
        lines.append(f"🔍 {escape(m.produto)}")
    lines.append(_linha_veredicto(v))
    if v.max_eur:
        lines.append(f"💶 Máximo {fmt_eur(v.max_eur)}")
    if v.max_montra_yen and v.max_montra_yen > 0:
        lines.append(f"💴 Pagaria no máximo {fmt_yen(v.max_montra_yen)}")
    japao = None if p.em_euros else _linha_japao(m, taxa)
    lines += [linha for linha in (_linha_europa(m, taxa), japao) if linha]
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


_CURTO = _CABECALHO


def resumo(
    c: Contas, m: Mercado, v: Veredicto, criado_em: float | None, agora: float, *, estado: str = "desconhecido",
    preco_eur: float | None = None,
) -> str:
    """Resultado compacto para ler de pé na loja (o artigo já aparece citado por cima)."""
    euros = preco_eur is not None  # modo Europa: sem importação nem Japão
    taxa = c.montra_eur / c.montra_yen if c.montra_eur and c.montra_yen and not euros else None
    cabecalho = _CURTO[v.codigo]
    if v.codigo.startswith("eu_"):
        lines = [_linha_veredicto_eur(v)]
    elif v.codigo.startswith("jp_") or v.codigo == "incerto" or v.poupanca_eur is None:
        lines = [f"{cabecalho} · {escape(v.motivo or '')}"]
    elif v.codigo == "nao":
        lines = [f"{cabecalho} · {_eur0(-v.poupanca_eur)} mais caro que na Europa"]
    else:
        lines = [f"{cabecalho} · poupas {_eur0(v.poupanca_eur)} ({round(v.poupanca_pct)}%)"]
    if v.max_montra_yen and v.max_montra_yen > 0:
        lines.append(f"💴 Máximo {fmt_yen(v.max_montra_yen)}")
    if v.max_eur:
        lines.append(f"💶 Máximo {_eur0(v.max_eur)}")
    # O link fica só no nome da fonte: os valores ficam em texto normal, para se lerem bem.
    europa = []
    if m.vinted_eur:
        europa.append(f"{_link('Vinted', m.vinted_url)} ~{_eur0(m.vinted_eur)} ({m.vinted_n})")
    if m.novo_eu_eur:
        loja = escape(loja_curta(m.novo_eu_loja) or "")
        if m.novo_eu_url.startswith("http"):
            loja = _link(loja or "loja", m.novo_eu_url)
        europa.append(f"novo {_eur0(m.novo_eu_eur)}" + (f" ({loja})" if loja else ""))
    if m.importar_yen and taxa is not None:
        europa.append(f"{_link('importar', m.importar_url)} ~{_eur0(importar_total_eur(m.importar_yen, taxa))}")
    if europa:
        lines.append("🇪🇺 " + " · ".join(europa))
    jp = None if euros else _intervalo(m.jp_min_yen, m.jp_max_yen, fmt_yen)
    if jp:
        linha = f"{_link('Mercari', m.mercari_url)} {'à venda ' if m.jp_so_pedidos else ''}{jp}"
        linha += f"{_mercari_em_eur(m, taxa)} ({m.jp_n})"
        lines.append(f"🇯🇵 {linha}" + (" · 👀 caro aqui" if v.caro_no_japao else ""))
    if m.produto:
        ver = f" · {_link('ver', m.produto_url)}" if m.produto_url.startswith("http") else ""
        lines.append(f"🔍 {escape(m.produto)}{ver}")
    if estado == "desconhecido":
        lines.append("❔ Sem estado: comparei como usado (✏️ Corrigir para afinar)")
    lines += [f"⚠️ {escape(aviso)}" for aviso in m.avisos]
    if criado_em is not None:
        lines.append(f"🕒 avaliado {_ha_quanto(agora - criado_em)}")
    return "\n".join(lines)


_EMOJI = {"compensa": "🟢", "pouca": "🟡", "nao": "🔴", "incerto": "⚪", "jp_bom": "🟢", "jp_normal": "🟡",
          "jp_caro": "🔴", "eu_bom": "🟢", "eu_normal": "🟡", "eu_caro": "🔴"}  # fmt: skip


def texto_historico(linhas) -> str:
    """/historico: as últimas avaliações, para rever no fim do dia (hora de Tóquio)."""
    if not linhas:
        return "Ainda não há avaliações."
    out = ["🧾 <b>Últimas avaliações</b> (hora de Tóquio)"]
    for linha in linhas:
        quando = datetime.fromtimestamp(linha["criado_em"], TOKYO).strftime("%d/%m %H:%M")
        preco = fmt_eur(linha["preco_eur"]) if linha["preco_eur"] is not None else fmt_yen(linha["preco_yen"])
        out.append(f"{_EMOJI.get(linha['veredicto'], '⚪')} {quando} · {escape(linha['nome'])} · {preco}")
    return "\n".join(out)
