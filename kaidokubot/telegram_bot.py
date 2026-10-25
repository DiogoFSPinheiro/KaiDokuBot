from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

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


def build_application(settings: Settings, storage: Storage, cambio: Cambio, http) -> Application:
    async def on_shutdown(_app: Application) -> None:
        await http.close()
        storage.close()

    app = Application.builder().token(settings.telegram_token).post_shutdown(on_shutdown).build()
    commands = Commands(storage, cambio)
    if settings.allowed_chat_id is None:
        log.warning("ALLOWED_CHAT_ID não definido: envia /id ao bot e põe o valor no .env")
    allowed = filters.Chat(chat_id=[] if settings.allowed_chat_id is None else [settings.allowed_chat_id])

    async def send(update: Update, r: Resposta) -> None:
        await update.effective_message.reply_text(
            r.texto, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup(r)
        )

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
        await send(update, commands.texto(chat_id, update.effective_message.text))

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
            else:
                r = commands.cancelar(chat_id, pedido_id)
            await edit(query, r.texto, r)

    app.add_handler(CommandHandler("id", on_id))
    app.add_handler(CommandHandler(["start", "help"], on_start, filters=allowed))
    app.add_handler(CommandHandler("cambio", on_cambio, filters=allowed))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & allowed, on_text))
    app.add_handler(CallbackQueryHandler(on_button, pattern=r"^(fix:\d+|fixf:\d+:(nome|preco|estado)|st:\d+:\d|fixx:\d+)$"))

    async def fx_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        await cambio.atualizar()

    app.job_queue.run_repeating(fx_job, interval=FX_JOB_INTERVAL_S, first=5, name="cambio")
    return app
