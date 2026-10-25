from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

ESTADOS: tuple[str, ...] = ("selado", "novo", "usado", "sem caixa", "caixa danificada", "desconhecido")

PRECO_MIN = 100  # nada custa menos (um gashapon custa ¥200+); evita apanhar medidas soltas
PRECO_MAX = 10_000_000
PRECO_EUR_MIN = 1
PRECO_EUR_MAX = 100_000
FALTA_PRECO = "Falta o preço. Exemplo: nendoroid frieren 4800 (ou 30€, em Portugal)"

# Palavras-chave por estado (pt-PT / inglês / japonês). Comparadas sem distinguir maiúsculas.
_PALAVRAS = {
    "selado": ["selado", "selada", "sealed", "misb", "nib", "新品未開封", "未開封"],
    "novo": ["novo", "nova", "new", "新品", "未使用"],
    "usado": [
        "usado", "usada", "used", "aberto", "aberta", "opened", "中古", "開封済み", "開封済", "開封品", "開封",
        # "caixa ok" numa loja de usados = usado e completo
        "caixa ok", "com caixa", "completo", "completa", "complete", "boxed", "box ok", "箱あり", "箱付き",
    ],
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

# "." e "," seguidos de 3 dígitos são milhares (o iene não tem decimais); seguidos de 1–2 dígitos, cêntimos (€).
_RE_PRECO = re.compile(
    r"(?<![a-z0-9])(?P<pre>[¥€]\s*)?"
    r"(?P<num>\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    r"(?P<pos>\s*(?:円|yen|jpy|€|euros?|eur))?(?![a-z0-9])",
    re.IGNORECASE,
)

# Unidade a seguir a um número (com ou sem espaço) ou o início de uma escala («1/7»).
_RE_UNIDADE = re.compile(r"\s*(?:(?:cm|mm|kg|g|ml|inch)(?![a-z])|センチ|号|/)", re.IGNORECASE)


class ParseError(Exception):
    """Erro com uma mensagem pronta a mostrar ao utilizador."""


@dataclass(frozen=True)
class Pedido:
    nome: str
    preco_yen: int  # 0 nos pedidos em euros
    estado: str
    preco_eur: float | None = None  # preço em € → modo Europa (em Portugal: sem Japão nem tax-free)

    @property
    def em_euros(self) -> bool:
        return self.preco_eur is not None


def _normalizar(texto: str) -> str:
    # NFKC converte os dígitos e o ￥ de largura total do teclado japonês.
    return unicodedata.normalize("NFKC", texto)


def _e_medida(texto: str, match: re.Match) -> bool:
    """«17 cm», «250 g», escalas «1/7»: números que não são o preço."""
    return bool(_RE_UNIDADE.match(texto, match.end())) or texto[: match.start()].endswith("/")


def _encontrar_preco(texto: str) -> re.Match | None:
    matches = [m for m in _RE_PRECO.finditer(texto) if m["pre"] or m["pos"] or not _e_medida(texto, m)]
    marcados = [m for m in matches if m["pre"] or m["pos"]]
    if marcados:
        return marcados[-1]
    return matches[-1] if matches else None


def _valor(match: re.Match) -> float:
    num = match["num"]
    centimos = re.search(r"[.,](\d{1,2})$", num)
    inteiro = num[: centimos.start()] if centimos else num
    valor = float(re.sub(r"[.,]", "", inteiro))
    return valor + int(centimos.group(1)) / 10 ** len(centimos.group(1)) if centimos else valor


def _moeda(match: re.Match) -> str:
    marcador = f"{match['pre'] or ''}{match['pos'] or ''}".lower()
    return "EUR" if "€" in marcador or "eur" in marcador else "JPY"


def _valido(valor: float, moeda: str) -> bool:
    if moeda == "EUR":
        return PRECO_EUR_MIN <= valor <= PRECO_EUR_MAX
    return PRECO_MIN <= valor <= PRECO_MAX


def parse_preco_moeda(texto: str) -> tuple[float, str] | None:
    """(valor, "JPY" | "EUR"); sem moeda é iene. None se não houver preço válido."""
    match = _encontrar_preco(_normalizar(texto))
    if match is None:
        return None
    valor, moeda = _valor(match), _moeda(match)
    if not _valido(valor, moeda):
        return None
    return (round(valor, 2), "EUR") if moeda == "EUR" else (int(round(valor)), "JPY")


def parse_preco(texto: str) -> int | None:
    """Preço em ienes (None se não houver, ou se estiver em euros)."""
    resultado = parse_preco_moeda(texto)
    return int(resultado[0]) if resultado and resultado[1] == "JPY" else None


def e_so_preco(texto: str) -> bool:
    """O texto é só um preço (ex.: «¥5,200»), sem nome nem estado."""
    match = _RE_PRECO.search(texto := _normalizar(texto).strip())
    return match is not None and match.span() == (0, len(texto))


def _estado_de(matches: list[re.Match]) -> str:
    encontrados = {_ESTADO_DE[m.group(0).lower()] for m in matches}
    return next((estado for estado in _PRIORIDADE if estado in encontrados), "desconhecido")


def parse_estado(texto: str) -> str:
    return _estado_de(list(_RE_ESTADO.finditer(_normalizar(texto))))


def parse_pedido(texto: str) -> Pedido:
    texto = _normalizar(texto)
    preco = _encontrar_preco(texto)
    if preco is None:
        raise ParseError(FALTA_PRECO)
    valor, moeda = _valor(preco), _moeda(preco)
    if valor < PRECO_MIN and not (preco["pre"] or preco["pos"]):
        # Ex.: «switch 2» sem preço: o «2» não é um preço.
        raise ParseError(FALTA_PRECO)
    if not _valido(valor, moeda):
        if moeda == "EUR":
            raise ParseError(f"O preço tem de estar entre €{PRECO_EUR_MIN} e €{PRECO_EUR_MAX:,}.".replace(",", "."))
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
    if moeda == "EUR":
        return Pedido(nome=nome, preco_yen=0, estado=_estado_de(estados), preco_eur=round(valor, 2))
    return Pedido(nome=nome, preco_yen=int(round(valor)), estado=_estado_de(estados))
