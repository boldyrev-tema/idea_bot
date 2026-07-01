import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

# ── настройки ──────────────────────────────────────────────────────────────────
TOKEN = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://boldyrev-tema.github.io/idea_bot/")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── /start — открыть Mini App ───────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Открыть 🎯", web_app=WebAppInfo(url=WEBAPP_URL))]]
    )
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋 Подскажу, куда сходить с друзьями, "
        "если не хочется тратить много денег.",
        reply_markup=keyboard,
    )


# ── точка входа ────────────────────────────────────────────────────────────────
def main():
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    logger.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
