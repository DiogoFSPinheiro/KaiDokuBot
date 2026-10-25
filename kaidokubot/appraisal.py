"""Avaliação por IA: compensa comprar aqui em vez de na Europa? E está caro para o Japão?"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from urllib.parse import quote_plus

from kaidokubot.claude import ClaudeError
from kaidokubot.commands import NAO_EXISTE, Resposta
from kaidokubot.fontes import Anuncio, FonteError
from kaidokubot.formatting import fmt_eur, fmt_yen, resultado
from kaidokubot.fx import Cambio
from kaidokubot.parsing import Pedido
from kaidokubot.rules import Mercado, calcular_veredicto, contas
from kaidokubot.storage import Storage, chave_cache, inicio_do_dia_tokyo

log = logging.getLogger(__name__)

MAX_VENDIDOS = 40
MAX_A_VENDA = 20
MAX_VINTED = 30

SYSTEM_TERMOS = "Convertes nomes de artigos de merch japonesa nos termos de pesquisa usados no mercado. És conciso."
SYSTEM_MERCADO = (
    "Ajudas um colecionador português, numa loja no Japão, a decidir se compensa comprar um artigo ali "
    "em vez de o comprar na Europa. Nunca inventas números: usas null quando não tens dados fiáveis. "
    "Respondes sempre em português de Portugal, de forma concisa."
)

_N = {"type": ["number", "null"]}
_S = {"type": ["string", "null"]}

SCHEMA_TERMOS = {
    "title": "termos",
    "type": "object",
    "properties": {
        "termo_jp": {"type": "string", "description": "Como aparece nos anúncios do Mercari Japão, 2–4 palavras"},
        "termo_en": {"type": "string", "description": "Como apareceria num anúncio europeu, 2–4 palavras"},
    },
    "required": ["termo_jp", "termo_en"],
}

SCHEMA_MERCADO = {
    "title": "mercado",
    "type": "object",
    "properties": {
        "novo_eu_eur": {**_N, "description": "Preço novo mais baixo numa loja europeia que envie para Portugal"},
        "novo_eu_loja": {**_S, "description": "Só o nome da loja, 1–3 palavras (ex.: Amazon.es)"},
        "vinted_min_eur": {**_N, "description": "Intervalo típico dos anúncios comparáveis da Vinted, mesmo estado"},
        "vinted_max_eur": _N,
        "vinted_tipico_eur": {**_N, "description": "Mediana dos anúncios comparáveis da Vinted, mesmo estado"},
        "vinted_n": {"type": "integer", "description": "Quantos anúncios da Vinted são comparáveis"},
        "importar_yen": {**_N, "description": "Preço numa loja online japonesa que envie para a Europa"},
        "importar_loja": {**_S, "description": "Só o nome da loja, 1–3 palavras (ex.: AmiAmi)"},
        "jp_min_yen": {**_N, "description": "Intervalo típico no Mercari, mesmo estado"},
        "jp_max_yen": _N,
        "jp_n": {"type": "integer", "description": "Quantos anúncios do Mercari usaste"},
        "jp_so_pedidos": {"type": "boolean", "description": "true se não houve vendidos comparáveis"},
        "cenarios": {
            "type": "array",
            "description": "Só com estado desconhecido: os cenários principais",
            "items": {
                "type": "object",
                "properties": {"estado": {"type": "string"}, "eu_min": _N, "eu_max": _N, "jp_min": _N, "jp_max": _N},
                "required": ["estado", "eu_min", "eu_max", "jp_min", "jp_max"],
            },
        },
        "razao": {"type": "string", "description": "No máximo 2 frases curtas (≤ 250 caracteres)"},
        "fontes": {
            "type": "array",
            "description": "2–4 páginas que usaste",
            "items": {
                "type": "object",
                "properties": {"nome": {"type": "string"}, "url": {"type": "string"}},
                "required": ["nome", "url"],
            },
        },
    },
    "required": [
        "novo_eu_eur", "novo_eu_loja", "vinted_min_eur", "vinted_max_eur", "vinted_tipico_eur", "vinted_n", "importar_yen",
        "importar_loja", "jp_min_yen", "jp_max_yen", "jp_n", "jp_so_pedidos", "cenarios", "razao", "fontes",
    ],
}  # fmt: skip


def prompt_termos(pedido: Pedido) -> str:
    return (
        f"Artigo escrito por um turista (pode estar em português, inglês, romaji ou japonês): «{pedido.nome}».\n"
        "termo_jp: o nome como aparece nos anúncios do Mercari Japão, curto e sem estado nem preço "
        "(ex.: ねんどろいど フリーレン, ポップアップパレード フェルン, ゼルダの伝説 ティアーズオブザキングダム).\n"
        "termo_en: o nome em inglês como apareceria num anúncio europeu (ex.: nendoroid frieren, zelda tears of the kingdom)."
    )


def _lista(anuncios: list[Anuncio] | None, fmt: Callable[[float], str]) -> list[str]:
    if anuncios is None:
        return ["(indisponível)"]
    return [f"- {a.titulo} | {fmt(a.preco)} | {a.estado}" for a in anuncios] or ["(nenhum)"]


def prompt_mercado(
    pedido: Pedido, termos: dict, vendidos: list[Anuncio] | None, a_venda: list[Anuncio] | None,
    vinted: list[Anuncio] | None,
) -> str:  # fmt: skip
    lines = [
        f"Artigo: {pedido.nome} (termo japonês: {termos['termo_jp']}; inglês: {termos['termo_en']}).",
        f"Estado: {pedido.estado}.",
        f"Estou numa loja no Japão e custa {fmt_yen(pedido.preco_yen)} (preço de montra, com imposto). "
        "Quero saber quanto me custaria na Europa (vivo em Portugal) e se o preço é normal para o Japão.",
        "",
        "Mercari Japão — VENDIDOS (vendas concluídas):",
        *_lista(vendidos, fmt_yen),
        "",
        "Mercari Japão — À VENDA (preços pedidos):",
        *_lista(a_venda, fmt_yen),
        "",
        "Vinted (Europa; preços pedidos em € com a proteção do comprador, sem portes):",
        *_lista(vinted, fmt_eur),
        "",
        "Muitos destes anúncios não são comparáveis (outro artigo ou personagem, minis/さぷらいず, lotes, "
        "peças soltas, outro estado): ignora-os.",
        "1. Mercari: intervalo típico (¥) dos VENDIDOS comparáveis no mesmo estado (jp_min_yen, jp_max_yen, jp_n). "
        "Se não houver vendidos comparáveis, usa os à venda e jp_so_pedidos=true.",
        "2. Vinted: intervalo típico (€) dos anúncios comparáveis no mesmo estado (vinted_min_eur, vinted_max_eur, "
        "vinted_n) e a mediana desses anúncios (vinted_tipico_eur).",
        "3. Pesquisar na web é obrigatório (2 a 5 pesquisas, em inglês e japonês): o preço novo mais baixo numa "
        "loja europeia que envie para Portugal (ex.: Amazon.es/.de/.fr, Fnac, JapanDco, Nin-Nin-Game, Figurine "
        "Universe; para jogos e consolas também KuantoKusta e Worten) e o preço numa loja online japonesa que envie "
        "para a Europa (AmiAmi, HobbySearch, Good Smile Online, Play-Asia), em ienes. Só preços ATUAIS vistos na "
        "página da própria loja: nada de notícias, promoções acabadas ou preços de lançamento (PVP).",
        "4. Ajusta ao estado: selado/novo compara com novos; usado, sem caixa ou caixa danificada valem menos. "
        "Com estado desconhecido, preenche cenarios com os cenários principais (ex.: selado e usado) e usa nos "
        "campos principais o mais provável numa loja de usados. Senão, cenarios fica vazio.",
        "5. Nunca inventes números: null no que não encontrares. razao: no máximo 2 frases curtas para ler de pé "
        "numa loja (de onde vêm os números e se só havia preços pedidos). fontes: 2 a 4 páginas que usaste.",
    ]
    return "\n".join(lines)


def _numero(valor) -> float | None:
    if valor is None:
        return None
    numero = float(valor)
    return numero if numero > 0 else None


def mercado_de(dados: dict, termos: dict, avisos: list[str]) -> Mercado:
    try:
        return Mercado(
            termo_jp=str(termos["termo_jp"]),
            termo_en=str(termos["termo_en"]),
            novo_eu_eur=_numero(dados["novo_eu_eur"]),
            novo_eu_loja=dados.get("novo_eu_loja") or None,
            vinted_min_eur=_numero(dados["vinted_min_eur"]),
            vinted_max_eur=_numero(dados["vinted_max_eur"]),
            vinted_tipico_eur=_numero(dados.get("vinted_tipico_eur")),
            vinted_n=int(dados.get("vinted_n") or 0),
            importar_yen=_numero(dados["importar_yen"]),
            importar_loja=dados.get("importar_loja") or None,
            jp_min_yen=_numero(dados["jp_min_yen"]),
            jp_max_yen=_numero(dados["jp_max_yen"]),
            jp_n=int(dados.get("jp_n") or 0),
            jp_so_pedidos=bool(dados.get("jp_so_pedidos")),
            cenarios=[c for c in dados.get("cenarios") or [] if isinstance(c, dict)],
            razao=str(dados.get("razao") or ""),
            fontes=[f for f in dados.get("fontes") or [] if isinstance(f, dict) and f.get("nome") and f.get("url")],
            avisos=avisos,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ClaudeError("resposta incompleta do Claude") from exc


class Avaliador:
    def __init__(
        self, storage: Storage, cambio: Cambio, runner, mercari, vinted, *, max_dia: int, margem: int,
        cache_dias: int, now: Callable[[], float] = time.time,
    ) -> None:  # fmt: skip
        self._storage = storage
        self._cambio = cambio
        self._runner = runner
        self._mercari = mercari
        self._vinted = vinted
        self._max_dia = max_dia
        self._margem = margem
        self._cache_s = cache_dias * 86400
        self._now = now
        self._lock = asyncio.Lock()
        self._na_fila = 0  # pedidos à espera ou a correr

    async def avaliar(
        self, chat_id: int, pedido_id: int, forcar: bool, progresso: Callable[[str], None]
    ) -> Resposta:
        """Nunca lança: erros viram uma Resposta com a explicação."""
        pedido = self._storage.get_pedido(pedido_id)
        if pedido is None:
            return Resposta(NAO_EXISTE)
        chave = chave_cache(pedido.nome, pedido.estado)
        if not forcar and (cache := self._da_cache(chave)):
            return self._registar(chat_id, pedido_id, pedido, chave, *cache, da_cache=True)
        if self._storage.contar_avaliacoes(inicio_do_dia_tokyo(self._now())) >= self._max_dia:
            plural = "avaliação" if self._max_dia == 1 else "avaliações"
            return Resposta(
                f"⛔ Atingiste o limite de {self._max_dia} {plural} por dia (MAX_AVALIACOES_DIA). "
                "Volta à meia-noite de Tóquio; as respostas da cache continuam a funcionar."
            )
        posicao = self._na_fila
        self._na_fila += 1
        try:
            if posicao:
                progresso(f"⏳ Na fila (posição {posicao})…")
            async with self._lock:
                # Enquanto esperava, outro pedido pode ter avaliado o mesmo artigo.
                if not forcar and (cache := self._da_cache(chave)):
                    return self._registar(chat_id, pedido_id, pedido, chave, *cache, da_cache=True)
                mercado = await self._pesquisar(pedido, progresso)
        except ClaudeError as exc:
            return Resposta(f"❌ Não consegui avaliar: {exc}", [[("💡 Tentar outra vez", f"av:{pedido_id}")]])
        except Exception:
            log.exception("Falha ao avaliar o pedido %s", pedido_id)
            return Resposta(
                "❌ Não consegui avaliar (erro inesperado, vê o log).", [[("💡 Tentar outra vez", f"av:{pedido_id}")]]
            )
        finally:
            self._na_fila -= 1
        return self._registar(chat_id, pedido_id, pedido, chave, mercado, None, da_cache=False)

    def _da_cache(self, chave: str) -> tuple[Mercado, float] | None:
        encontrado = self._storage.cache(chave, desde=self._now() - self._cache_s)
        if encontrado is None:
            return None
        mercado_json, criado_em = encontrado
        try:
            return Mercado.from_dict(json.loads(mercado_json)), criado_em
        except (TypeError, ValueError):
            log.warning("Cache inválida para %s; a ignorar", chave)
            return None

    def _registar(
        self, chat_id: int, pedido_id: int, pedido: Pedido, chave: str, mercado: Mercado, criado_em: float | None,
        *, da_cache: bool,
    ) -> Resposta:  # fmt: skip
        taxa = self._cambio.taxa()
        c = contas(pedido.preco_yen, taxa)
        veredicto = calcular_veredicto(mercado, c, taxa, self._margem)
        mercado_json = json.dumps(mercado.to_dict(), ensure_ascii=False)
        self._storage.add_avaliacao(
            chat_id, pedido_id, pedido, chave, mercado_json, veredicto.codigo, da_cache, now=self._now()
        )
        texto = resultado(pedido, c, mercado, veredicto, criado_em, self._now())
        return Resposta(texto, [[("🔄 Reavaliar", f"rv:{pedido_id}"), ("✏️ Corrigir", f"fix:{pedido_id}")]])

    async def _pesquisar(self, pedido: Pedido, progresso: Callable[[str], None]) -> Mercado:
        progresso("🈂️ A preparar a pesquisa…")
        termos = await self._runner.run(prompt_termos(pedido), SCHEMA_TERMOS, system=SYSTEM_TERMOS)
        if not termos.get("termo_jp") or not termos.get("termo_en"):
            raise ClaudeError("resposta incompleta do Claude")
        progresso(f"🔎 A procurar no Mercari ({termos['termo_jp']}) e na Vinted ({termos['termo_en']})…")
        mercari, vinted = await asyncio.gather(
            self._mercari.procurar(termos["termo_jp"]), self._vinted.procurar(termos["termo_en"]),
            return_exceptions=True,
        )  # fmt: skip
        avisos = []
        vendidos = a_venda = anuncios_vinted = None
        if isinstance(mercari, BaseException):
            log.warning("Mercari falhou: %s", mercari)
            avisos.append("Mercari indisponível")
        else:
            vendidos, a_venda = mercari[0][:MAX_VENDIDOS], mercari[1][:MAX_A_VENDA]
        if isinstance(vinted, BaseException):
            log.warning("Vinted falhou: %s", vinted)
            avisos.append("Vinted indisponível")
        else:
            anuncios_vinted = vinted[:MAX_VINTED]
        if isinstance(mercari, BaseException) and not isinstance(mercari, FonteError):
            log.error("Erro inesperado no Mercari", exc_info=mercari)
        resumo = (
            f"🔎 Mercari: {len(vendidos) if vendidos is not None else '–'} vendidos · "
            f"Vinted: {len(anuncios_vinted) if anuncios_vinted is not None else '–'} anúncios"
        )
        progresso(f"{resumo}\n🌐 A pesquisar lojas na web…")

        def on_search(query: str) -> None:
            progresso(f"{resumo}\n🌐 A pesquisar: {query}")

        dados = await self._runner.run(
            prompt_mercado(pedido, termos, vendidos, a_venda, anuncios_vinted), SCHEMA_MERCADO,
            system=SYSTEM_MERCADO, tools="WebSearch", on_search=on_search,
        )  # fmt: skip
        mercado = mercado_de(dados, termos, avisos)
        # Links para eu ver os anúncios do Mercari e da Vinted.
        extras = []
        if vendidos is not None:
            url = f"https://jp.mercari.com/search?keyword={quote_plus(mercado.termo_jp)}&status=sold_out"
            extras.append({"nome": "Mercari vendidos", "url": url})
        if anuncios_vinted is not None:
            url = f"https://www.vinted.pt/catalog?search_text={quote_plus(mercado.termo_en)}"
            extras.append({"nome": "Vinted", "url": url})
        return Mercado.from_dict({**mercado.to_dict(), "fontes": mercado.fontes[:4] + extras})
