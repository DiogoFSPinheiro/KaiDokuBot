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

    async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await send(update, commands.texto(update.effective_chat.id, update.effective_message.text))

    async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if update.effective_chat is None or update.effective_chat.id != settings.allowed_chat_id:
            return
        chat_id = update.effective_chat.id
        kind, *args = query.data.split(":")
        if kind == "fix":
            r = commands.menu_corrigir(int(args[0]))
        elif kind == "fixf":
            r = commands.pedir_campo(chat_id, int(args[0]), args[1])
        elif kind == "st":
            r = commands.definir_estado(int(args[0]), int(args[1]))
        else:
            r = commands.cancelar(chat_id)
        if kind in ("fix", "fixf"):
            await send(update, r)
            return
        # Escolha final (estado / cancelar): substitui o menu para não ficarem botões soltos.
        try:
            await query.edit_message_text(
                r.texto, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup(r)
            )
        except BadRequest:
            await send(update, r)

    app.add_handler(CommandHandler("id", on_id))
    app.add_handler(CommandHandler(["start", "help"], on_start, filters=allowed))
    app.add_handler(CommandHandler("cambio", on_cambio, filters=allowed))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & allowed, on_text))
    app.add_handler(CallbackQueryHandler(on_button, pattern=r"^(fix:\d+|fixf:\d+:(nome|preco|estado)|st:\d+:\d|fixx)$"))

    async def fx_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        await cambio.atualizar()

    app.job_queue.run_repeating(fx_job, interval=FX_JOB_INTERVAL_S, first=5, name="cambio")
    return app
