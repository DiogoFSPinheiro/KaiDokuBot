"""API de linha de comandos para a Wintermute ver preços (só leitura: sem Telegram, sem Claude, sem DB).

    python -m kaidokubot.api precos --termo=T [--termo-jp=J]

Pesquisa o Mercari (com o termo japonês, ou o termo se não vier), a Vinted e o KuantoKusta em paralelo e escreve
uma linha de JSON no stdout: {"termo", "mercari": {"vendidos", "a_venda"} | null, "vinted": [...] | null,
"kuantokusta": [...] | null}, no máximo POR_FONTE anúncios por lista. Uma fonte que falha vem null ([] é "sem
resultados"). Pedido inválido: {"erro": "..."} com código de saída 1.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from kaidokubot.fontes import Anuncio

log = logging.getLogger(__name__)

TERMO_MAX = 100
POR_FONTE = 5
# Por fonte: a Vinted pode demorar 20 s a aquecer e outros 20 s nos itens; a Wintermute espera 40 s pelo todo.
PRAZO_S = 25


class ErroApi(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # o argparse sairia com código 2 e texto no stderr
        raise ErroApi(f"Pedido inválido: {message}")


def _parser() -> _Parser:
    parser = _Parser(prog="python -m kaidokubot.api")
    ops = parser.add_subparsers(dest="op", required=True, parser_class=_Parser)
    precos = ops.add_parser("precos")
    precos.add_argument("--termo", required=True)
    precos.add_argument("--termo-jp", default="")
    return parser


def _limpo(texto: str, campo: str, obrigatorio: bool) -> str:
    texto = " ".join(texto.split())
    if obrigatorio and not texto:
        raise ErroApi(f"O {campo} está vazio.")
    if len(texto) > TERMO_MAX:
        raise ErroApi(f"O {campo} tem mais de {TERMO_MAX} caracteres.")
    return texto


def _json(anuncios: list[Anuncio], moeda: str) -> list[dict]:
    return [
        {"titulo": a.titulo, "preco": a.preco, "moeda": moeda, "estado": a.estado, "url": a.url}
        for a in anuncios[:POR_FONTE]
    ]


def _ou_null(resultado, nome: str):
    if isinstance(resultado, BaseException):
        log.warning("%s falhou: %s", nome, resultado)
        return None
    return resultado


async def executar(argv: list[str], mercari, vinted, kuantokusta, prazo_s: float = PRAZO_S) -> tuple[int, dict]:
    """(código de saída, JSON). Nunca levanta por causa do pedido nem das fontes; uma fonte que passa de
    `prazo_s` vem null sem estragar as outras."""
    try:
        args = _parser().parse_args(argv)
        termo = _limpo(args.termo, "termo", obrigatorio=True)
        termo_jp = _limpo(args.termo_jp, "termo japonês", obrigatorio=False)
    except ErroApi as exc:
        return 1, {"erro": str(exc)}
    m, v, k = await asyncio.gather(
        *(asyncio.wait_for(pedido, prazo_s) for pedido in (
            mercari.procurar(termo_jp or termo), vinted.procurar(termo), kuantokusta.procurar(termo),
        )),
        return_exceptions=True,
    )  # fmt: skip
    m, v, k = _ou_null(m, "Mercari"), _ou_null(v, "Vinted"), _ou_null(k, "KuantoKusta")
    return 0, {
        "termo": termo,
        "mercari": None if m is None else {"vendidos": _json(m[0], "JPY"), "a_venda": _json(m[1], "JPY")},
        "vinted": None if v is None else _json(v, "EUR"),
        "kuantokusta": None if k is None else _json(k, "EUR"),
    }


async def _principal(argv: list[str]) -> tuple[int, dict]:
    from kaidokubot.fontes import KuantoKusta, Mercari, Vinted

    mercari, vinted, kuantokusta = Mercari(), Vinted(), KuantoKusta()
    try:
        return await executar(argv, mercari, vinted, kuantokusta)
    finally:
        for fonte in (mercari, vinted, kuantokusta):
            try:
                await fonte.close()
            except Exception:
                pass


def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    codigo, dados = asyncio.run(_principal(sys.argv[1:]))
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(dados, ensure_ascii=False))
    sys.exit(codigo)


if __name__ == "__main__":
    main()
