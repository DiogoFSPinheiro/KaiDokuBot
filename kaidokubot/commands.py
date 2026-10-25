from __future__ import annotations

from dataclasses import dataclass, field, replace

from kaidokubot.formatting import resposta_imediata, texto_cambio
from kaidokubot.fx import Cambio, parse_taxa
from kaidokubot.parsing import ESTADOS, PRECO_MAX, PRECO_MIN, ParseError, Pedido, e_so_preco, parse_pedido, parse_preco
from kaidokubot.rules import contas
from kaidokubot.storage import Storage

NAO_EXISTE = "Já não tenho esse pedido. Envia-o outra vez."


def _cancelar(pedido_id: int) -> tuple[str, str]:
    return ("Cancelar", f"fixx:{pedido_id}")


@dataclass(frozen=True)
class Resposta:
    texto: str  # HTML
    botoes: list[list[tuple[str, str]]] = field(default_factory=list)  # linhas de (rótulo, callback_data)


class Commands:
    """Comportamento do bot, sem depender do Telegram (os botões são callback_data)."""

    def __init__(self, storage: Storage, cambio: Cambio) -> None:
        self._storage = storage
        self._cambio = cambio
        # Correção em curso por chat: (id do pedido, "nome" | "preco").
        self._esperando: dict[int, tuple[int, str]] = {}

    def botoes_pedido(self, pedido_id: int) -> list[list[tuple[str, str]]]:
        return [[("✏️ Corrigir", f"fix:{pedido_id}")]]

    def _imediata(self, pedido_id: int, pedido: Pedido) -> Resposta:
        texto = resposta_imediata(pedido, contas(pedido.preco_yen, self._cambio.taxa()))
        return Resposta(texto, self.botoes_pedido(pedido_id))

    def texto(self, chat_id: int, texto: str) -> Resposta:
        esperando = self._esperando.pop(chat_id, None)
        if esperando is not None:
            resposta = self._corrigir(chat_id, *esperando, texto)
            if resposta is not None:
                return resposta
        try:
            pedido = parse_pedido(texto)
        except ParseError as exc:
            return Resposta(str(exc))
        return self._imediata(self._storage.add_pedido(chat_id, pedido), pedido)

    def _corrigir(self, chat_id: int, pedido_id: int, campo: str, texto: str) -> Resposta | None:
        """Aplica a correção; None se o texto não for uma correção (e então é um pedido novo)."""
        pedido = self._storage.get_pedido(pedido_id)
        if pedido is None:
            return None
        if campo == "nome":
            nome = " ".join(texto.split())
            if not nome:
                return None
            pedido = replace(pedido, nome=nome)
        else:
            if not e_so_preco(texto):
                return None
            preco = parse_preco(texto)
            if preco is None:
                self._esperando[chat_id] = (pedido_id, campo)
                return Resposta(f"O preço tem de estar entre ¥{PRECO_MIN} e ¥{PRECO_MAX:,}.".replace(",", "."))
            pedido = replace(pedido, preco_yen=preco)
        self._storage.update_pedido(pedido_id, pedido)
        return self._imediata(pedido_id, pedido)

    def menu_corrigir(self, pedido_id: int) -> Resposta:
        if self._storage.get_pedido(pedido_id) is None:
            return Resposta(NAO_EXISTE)
        campos = [("Nome", "nome"), ("Preço", "preco"), ("Estado", "estado")]
        return Resposta(
            "O que queres corrigir?",
            [[(rotulo, f"fixf:{pedido_id}:{campo}") for rotulo, campo in campos], [_cancelar(pedido_id)]],
        )

    def pedir_campo(self, chat_id: int, pedido_id: int, campo: str) -> Resposta:
        if self._storage.get_pedido(pedido_id) is None:
            return Resposta(NAO_EXISTE)
        if campo == "estado":
            botoes = [(estado, f"st:{pedido_id}:{i}") for i, estado in enumerate(ESTADOS)]
            return Resposta("Qual é o estado?", [botoes[i : i + 2] for i in range(0, len(botoes), 2)] + [[_cancelar(pedido_id)]])
        self._esperando[chat_id] = (pedido_id, campo)
        pergunta = "Escreve o nome certo:" if campo == "nome" else "Escreve o preço certo (ex.: 4800):"
        return Resposta(pergunta, [[_cancelar(pedido_id)]])

    def definir_estado(self, pedido_id: int, indice: int) -> Resposta:
        pedido = self._storage.get_pedido(pedido_id)
        if pedido is None:
            return Resposta(NAO_EXISTE)
        if not 0 <= indice < len(ESTADOS):
            return Resposta("Estado inválido.")
        pedido = replace(pedido, estado=ESTADOS[indice])
        self._storage.update_pedido(pedido_id, pedido)
        return self._imediata(pedido_id, pedido)

    def cancelar(self, chat_id: int, pedido_id: int) -> Resposta:
        self._esperando.pop(chat_id, None)
        pedido = self._storage.get_pedido(pedido_id)
        return Resposta(NAO_EXISTE) if pedido is None else self._imediata(pedido_id, pedido)

    async def cambio(self, args: list[str]) -> str:
        if not args:
            return texto_cambio(self._cambio.estado())
        if len(args) == 1 and args[0].lower() == "auto":
            return "✅ Câmbio automático.\n" + texto_cambio(await self._cambio.voltar_auto())
        taxa = parse_taxa(args[0]) if len(args) == 1 else None
        if taxa is None:
            return "Uso: /cambio (ver) · /cambio 0.0058 (fixar ¥→€) · /cambio auto (automático)"
        self._cambio.definir_manual(taxa)
        return "✅ Câmbio fixado.\n" + texto_cambio(self._cambio.estado())
