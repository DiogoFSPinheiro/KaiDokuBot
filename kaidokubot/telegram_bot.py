from __future__ import annotations

import asyncio
import html
import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, RetryAfter
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from kaidokubot.appraisal import Avaliador
from kaidokubot.commands import Commands, Resposta
from kaidokubot.config import Settings
from kaidokubot.formatting import HELP
from kaidokubot.fx import Cambio
from kaidokubot.storage import Storage

log = logging.getLogger(__name__)

FX_JOB_INTERVAL_S = 6 * 3600  # o Cambio só vai à rede se a última atualização tiver mais de 20 h


def markup(r: Resposta) -> InlineKeyboardMarkup | None:
    if not r.botoes:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(rotulo, callback_data=data) for rotulo, data in linha] for linha in r.botoes]
    )


class Progresso:
    """Mensagem de progresso: mostra sempre o texto mais recente, com no máximo uma edição a cada `intervalo_s`."""

    def __init__(self, mensagem, intervalo_s: float = 3.0) -> None:
        self._mensagem = mensagem
        self._intervalo_s = intervalo_s
        self._texto: str | None = None
        self._mostrado: str | None = None
        self._ultima = float("-inf")
        self._tarefa: asyncio.Task | None = None
        self._fechado = False

    def __call__(self, texto: str) -> None:
        if self._fechado:
            return
        self._texto = texto
        if self._tarefa is None or self._tarefa.done():
            self._tarefa = asyncio.create_task(self._atualizar())

    async def _atualizar(self) -> None:
        loop = asyncio.get_running_loop()
        while self._texto != self._mostrado:
            espera = self._ultima + self._intervalo_s - loop.time()
            if espera > 0:
                await asyncio.sleep(espera)
            texto = self._texto
            try:
                await self._mensagem.edit_text(texto)
            except (BadRequest, RetryAfter) as exc:
                log.debug("Progresso não atualizado: %s", exc)
            self._mostrado = texto
            self._ultima = loop.time()

    async def fechar(self) -> None:
        self._fechado = True
        if self._tarefa is not None and not self._tarefa.done():
            self._tarefa.cancel()
            try:
                await self._tarefa
            except asyncio.CancelledError:
                pass


def build_application(
    settings: Settings, storage: Storage, cambio: Cambio, recursos: list, avaliador: Avaliador | None = None
) -> Application:
    async def on_shutdown(_app: Application) -> None:
        for recurso in recursos:  # clientes HTTP (câmbio, Mercari, Vinted)
            await recurso.close()
        storage.close()

    app = Application.builder().token(settings.telegram_token).post_shutdown(on_shutdown).build()
    # Com AUTO_AVALIAR cada pedido é avaliado logo; senão aparece o botão «💡 Avaliar».
    auto = avaliador is not None and settings.auto_avaliar
    commands = Commands(storage, cambio, avaliacao=avaliador is not None and not auto)
    if settings.allowed_chat_id is None:
        log.warning("ALLOWED_CHAT_ID não definido: envia /id ao bot e põe o valor no .env")
    allowed = filters.Chat(chat_id=[] if settings.allowed_chat_id is None else [settings.allowed_chat_id])

    async def send(update: Update, r: Resposta):
        return await update.effective_message.reply_text(
            r.texto, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup(r)
        )

    async def avaliar_em(mensagem, chat_id: int, pedido_id: int, forcar: bool) -> None:
        """Avalia o pedido numa mensagem de progresso que responde a `mensagem` e acaba com o resultado."""
        pendente = await mensagem.reply_text("🔎 A preparar a avaliação…", do_quote=True)
        progresso = Progresso(pendente)
        r = await avaliador.avaliar(chat_id, pedido_id, forcar, progresso)
        await progresso.fechar()
        try:
            await pendente.edit_text(
                r.texto, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup(r)
            )
        except BadRequest:
            # Nunca deixar a mensagem de progresso presa: manda o resultado numa mensagem nova, sem HTML.
            log.exception("Não consegui mostrar o resultado da avaliação %s", pedido_id)
            await pendente.reply_text(re.sub(r"<[^>]+>", "", html.unescape(r.texto)), reply_markup=markup(r))

    def avaliar_logo(context: ContextTypes.DEFAULT_TYPE, mensagem, chat_id: int, r: Resposta) -> None:
        if auto and r.pedido_id is not None:
            # Em segundo plano: a avaliação demora e não pode bloquear as respostas imediatas.
            context.application.create_task(avaliar_em(mensagem, chat_id, r.pedido_id, False))

    async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(HELP)

    async def on_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(f"O teu chat id é {update.effective_chat.id}")

    async def on_cambio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(await commands.cambio(context.args))

    # Mensagem que está a pedir o nome/preço certo, por chat: (message_id, texto HTML original).
    a_pedir: dict[int, tuple[int, str]] = {}

    async def fechar_pedido_de_texto(bot, chat_id: int) -> None:
        """Tira os botões e a pergunta da mensagem que pedia a correção (não deixa botões soltos)."""
        pendente = a_pedir.pop(chat_id, None)
        if pendente is None:
            return
        message_id, original = pendente
        try:
            await bot.edit_message_text(
                original, chat_id=chat_id, message_id=message_id, parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )  # fmt: skip
        except BadRequest:
            pass

    async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        await fechar_pedido_de_texto(context.bot, chat_id)
        r = commands.texto(chat_id, update.effective_message.text)
        avaliar_logo(context, await send(update, r), chat_id, r)

    async def edit(query, texto: str, r: Resposta) -> None:
        try:
            await query.edit_message_text(
                texto, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup(r)
            )
        except BadRequest as exc:  # ex.: "message is not modified"
            log.debug("Edição ignorada: %s", exc)

    async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if update.effective_chat is None or update.effective_chat.id != settings.allowed_chat_id:
            return
        chat_id = update.effective_chat.id
        kind, *args = query.data.split(":")
        pedido_id = int(args[0])
        # Os menus editam a própria mensagem do pedido, em vez de enviarem mensagens novas.
        original = query.message.text_html
        if kind == "fix":
            await edit(query, original, commands.menu_corrigir(pedido_id))
        elif kind == "fixf":
            r = commands.pedir_campo(chat_id, pedido_id, args[1])
            if args[1] == "estado":
                await edit(query, original, r)
            else:
                await fechar_pedido_de_texto(context.bot, chat_id)
                a_pedir[chat_id] = (query.message.message_id, original)
                await edit(query, f"{original}\n\n✏️ <i>{r.texto}</i>", r)
        else:
            if a_pedir.get(chat_id, (None,))[0] == query.message.message_id:
                a_pedir.pop(chat_id)
            if kind == "st":
                r = commands.definir_estado(pedido_id, int(args[1]))
                await edit(query, r.texto, r)
                avaliar_logo(context, query.message, chat_id, r)
            else:
                r = commands.cancelar(chat_id, pedido_id)
                await edit(query, r.texto, r)

    app.add_handler(CommandHandler("id", on_id))
    app.add_handler(CommandHandler(["start", "help"], on_start, filters=allowed))
    app.add_handler(CommandHandler("cambio", on_cambio, filters=allowed))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & allowed, on_text))
    app.add_handler(CallbackQueryHandler(on_button, pattern=r"^(fix:\d+|fixf:\d+:(nome|preco|estado)|st:\d+:\d|fixx:\d+)$"))

    if avaliador is not None:

        async def on_avaliar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            query = update.callback_query
            await query.answer()
            if update.effective_chat is None or update.effective_chat.id != settings.allowed_chat_id:
                return
            kind, pedido_id = query.data.split(":")
            await avaliar_em(query.message, update.effective_chat.id, int(pedido_id), kind == "rv")

        # block=False: a avaliação demora minutos e não pode bloquear as respostas imediatas.
        app.add_handler(CallbackQueryHandler(on_avaliar, pattern=r"^(av|rv):\d+$", block=False))

    async def fx_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        await cambio.atualizar()

    app.job_queue.run_repeating(fx_job, interval=FX_JOB_INTERVAL_S, first=5, name="cambio")
    return app
