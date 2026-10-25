from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

ESTADOS: tuple[str, ...] = ("selado", "novo", "usado", "sem caixa", "caixa danificada", "desconhecido")

PRECO_MIN = 1
PRECO_MAX = 10_000_000

# Palavras-chave por estado (pt-PT / inglês / japonês). Comparadas sem distinguir maiúsculas.
_PALAVRAS = {
    "selado": ["selado", "selada", "sealed", "misb", "nib", "新品未開封", "未開封"],
    "novo": ["novo", "nova", "new", "新品", "未使用"],
    "usado": ["usado", "usada", "used", "aberto", "aberta", "opened", "中古", "開封済み", "開封済", "開封品", "開封"],
    "sem caixa": ["sem caixa", "no box", "loose", "箱なし", "箱無し", "本体のみ"],
    "caixa danificada": [
        "caixa danificada", "caixa estragada", "damaged box", "box damage", "box damaged",
        "箱傷み", "箱痛み", "箱ダメージ", "箱潰れ",
    ],
}  # fmt: skip
# Com várias palavras no texto, ganha o estado mais específico.
_PRIORIDADE = ["caixa danificada", "sem caixa", "selado", "usado", "novo"]

_ESTADO_DE = {palavra.lower(): estado for estado, palavras in _PALAVRAS.items() for palavra in palavras}


def _padrao(palavra: str) -> str:
    # Palavras latinas só contam inteiras ("used" não apanha "unused"); o japonês não tem espaços.
    escaped = re.escape(palavra)
    return rf"(?<![a-z0-9]){escaped}(?![a-z0-9])" if palavra.isascii() else escaped


# A mais longa primeiro: "未開封" (selado) ganha a "開封" (usado), "新品未開封" ganha a "新品".
_RE_ESTADO = re.compile(
    "|".join(_padrao(p) for p in sorted(_ESTADO_DE, key=len, reverse=True)),
    re.IGNORECASE,
)

# O iene não tem decimais: "." e "," entre dígitos são sempre separadores de milhares.
_RE_PRECO = re.compile(
    r"(?<![a-z0-9])(?P<pre>¥\s*)?(?P<num>\d{1,3}(?:[.,]\d{3})+|\d+)(?P<pos>\s*(?:円|yen|jpy))?(?![a-z0-9])",
    re.IGNORECASE,
)


class ParseError(Exception):
    """Erro com uma mensagem pronta a mostrar ao utilizador."""


@dataclass(frozen=True)
class Pedido:
    nome: str
    preco_yen: int
    estado: str


def _normalizar(texto: str) -> str:
    # NFKC converte os dígitos e o ￥ de largura total do teclado japonês.
    return unicodedata.normalize("NFKC", texto)


def _encontrar_preco(texto: str) -> re.Match | None:
    matches = list(_RE_PRECO.finditer(texto))
    marcados = [m for m in matches if m["pre"] or m["pos"]]
    if marcados:
        return marcados[-1]
    return matches[-1] if matches else None


def _valor(match: re.Match) -> int:
    return int(re.sub(r"[.,]", "", match["num"]))


def parse_preco(texto: str) -> int | None:
    match = _encontrar_preco(_normalizar(texto))
    if match is None:
        return None
    valor = _valor(match)
    return valor if PRECO_MIN <= valor <= PRECO_MAX else None


def _estado_de(matches: list[re.Match]) -> str:
    encontrados = {_ESTADO_DE[m.group(0).lower()] for m in matches}
    return next((estado for estado in _PRIORIDADE if estado in encontrados), "desconhecido")


def parse_estado(texto: str) -> str:
    return _estado_de(list(_RE_ESTADO.finditer(_normalizar(texto))))


def parse_pedido(texto: str) -> Pedido:
    texto = _normalizar(texto)
    preco = _encontrar_preco(texto)
    if preco is None:
        raise ParseError("Falta o preço. Exemplo: nendoroid frieren 4800")
    valor = _valor(preco)
    if not PRECO_MIN <= valor <= PRECO_MAX:
        raise ParseError(f"O preço tem de estar entre ¥{PRECO_MIN} e ¥{PRECO_MAX:,}.".replace(",", "."))
    estados = list(_RE_ESTADO.finditer(texto))
    # O nome é o que sobra depois de tirar o preço e as palavras de estado.
    spans = sorted([preco.span(), *(m.span() for m in estados)], reverse=True)
    nome = texto
    for inicio, fim in spans:
        nome = nome[:inicio] + " " + nome[fim:]
    nome = " ".join(nome.split()).strip(" ,;:-·/")
    if not nome:
        raise ParseError("Falta o nome do artigo. Exemplo: nendoroid frieren 4800")
    return Pedido(nome=nome, preco_yen=valor, estado=_estado_de(estados))
