"""Foto da etiqueta ou da caixa → o que é, quanto custa e em que estado está."""

from __future__ import annotations

from dataclasses import dataclass

from kaidokubot.parsing import ESTADOS, PRECO_MAX, PRECO_MIN, parse_estado, parse_preco

SYSTEM_FOTO = (
    "Lês fotos de etiquetas de preço e de caixas de merch japonesa (figuras, peluches, jogos, consolas) tiradas "
    "em lojas no Japão. Nunca inventas: se não conseguires ler um campo, deixa-o vazio ou null."
)

PROMPT_FOTO = """Foto tirada numa loja no Japão (muitas vezes uma loja de usados: Mandarake, Suruga-ya, Book-Off, \
Lashinbang). Pode ser a etiqueta, a caixa ou as duas.
- nome: como um turista o escreveria, curto (ex.: «Nendoroid Frieren», «Zelda Tears of the Kingdom Switch»).
- fabricante, linha, personagem, referencia (só nº de catálogo ou versão): curtos, sem descrições.
- termo_jp: como aparece nos anúncios do Mercari Japão, específico (ex.: «ねんどろいど フリーレン 2367»).
- termo_en: como apareceria num anúncio europeu (ex.: «nendoroid frieren 2367»).
- preco_yen: o preço de venda. Se houver dois, o com imposto (税込). Ignora 税抜, números de catálogo, JAN e \
códigos de barras. null se não estiver visível.
- estado: selado (未開封, 新品未開封), novo (新品, 未使用), usado (中古, 開封, 開封品), sem caixa (箱なし, 本体のみ), \
caixa danificada (箱傷み, 箱ダメージ, 箱潰れ) ou desconhecido.
- confianca: alta se leste o nome e o preço sem dúvidas; baixa se a foto estiver desfocada ou cortada."""

_TEXTO = {"type": "string"}

SCHEMA_FOTO = {
    "title": "foto",
    "type": "object",
    "properties": {
        "nome": _TEXTO,
        "fabricante": _TEXTO,
        "linha": _TEXTO,
        "personagem": _TEXTO,
        "referencia": _TEXTO,
        "termo_jp": _TEXTO,
        "termo_en": _TEXTO,
        "preco_yen": {"type": ["integer", "null"]},
        "estado": {"type": "string", "enum": list(ESTADOS)},
        "confianca": {"type": "string", "enum": ["alta", "media", "baixa"]},
    },
    "required": [
        "nome", "fabricante", "linha", "personagem", "referencia", "termo_jp", "termo_en", "preco_yen", "estado",
        "confianca",
    ],
}  # fmt: skip

_CAMPOS_TERMOS = ("fabricante", "linha", "personagem", "referencia")


@dataclass(frozen=True)
class Leitura:
    nome: str
    preco_yen: int | None  # None se não foi possível ler
    estado: str
    confianca: str  # alta | media | baixa
    termos: dict  # identificação do produto, no formato do passo «identificar» da avaliação


def _preco(valor) -> int | None:
    try:
        preco = int(valor)
    except (TypeError, ValueError):
        return None
    return preco if PRECO_MIN <= preco <= PRECO_MAX else None


def leitura_de(dados: dict, legenda: str | None) -> Leitura:
    """Converte a resposta do Claude; a legenda (se tiver preço ou estado) ganha ao que foi lido."""
    termos = {campo: str(dados.get(campo) or "").strip() for campo in _CAMPOS_TERMOS}
    termos["referencia_url"] = None
    termos["termo_jp"] = str(dados.get("termo_jp") or "").strip()
    termos["termo_en"] = str(dados.get("termo_en") or "").strip()
    nome = str(dados.get("nome") or "").strip()
    if not nome:
        nome = " ".join(termos[campo] for campo in ("linha", "personagem", "referencia") if termos[campo])
    preco = _preco(dados.get("preco_yen"))
    estado = dados.get("estado") if dados.get("estado") in ESTADOS else "desconhecido"
    if legenda:
        preco = parse_preco(legenda) or preco
        estado_legenda = parse_estado(legenda)
        if estado_legenda != "desconhecido":
            estado = estado_legenda
    confianca = dados.get("confianca") if dados.get("confianca") in ("alta", "media", "baixa") else "baixa"
    return Leitura(nome or "?", preco, estado, confianca, termos)


async def ler_foto(runner, imagem: bytes, media_type: str, legenda: str | None) -> Leitura:
    """Lê a foto com o Claude (sem ferramentas: ~5 s)."""
    dados = await runner.run(PROMPT_FOTO, SCHEMA_FOTO, system=SYSTEM_FOTO, imagem=imagem, media_type=media_type)
    return leitura_de(dados, legenda)
