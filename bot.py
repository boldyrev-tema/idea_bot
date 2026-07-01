import logging
import os
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from ideas import BUDGET_LABELS, get_ideas_by_budget

# ── настройки ──────────────────────────────────────────────────────────────────
TOKEN = os.environ["BOT_TOKEN"]

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HELP_TEXT = (
    "Команды:\n"
    "/idea — получить идею, куда сходить с друзьями\n"
)

BUDGET_KEYBOARD = InlineKeyboardMarkup(
    [[InlineKeyboardButton(label, callback_data=f"budget:{key}")] for key, label in BUDGET_LABELS.items()]
)


# ── /start — сразу к делу, без лишнего шага ─────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋 Подскажу, куда сходить с друзьями, "
        "если не хочется тратить много денег.\n\n💰 Какой бюджет на компанию?",
        reply_markup=BUDGET_KEYBOARD,
    )


# ── /idea — то же самое для повторного использования ────────────────────────────
async def idea_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 Какой бюджет на компанию?", reply_markup=BUDGET_KEYBOARD)


# ── показать идею под выбранный бюджет ──────────────────────────────────────────
def _pick_idea(context: ContextTypes.DEFAULT_TYPE, budget: str) -> str:
    pool = get_ideas_by_budget(budget)
    last_text = context.user_data.get("last_idea")

    candidates = [i["text"] for i in pool if i["text"] != last_text] or [i["text"] for i in pool]
    text = random.choice(candidates)
    context.user_data["last_idea"] = text
    return text


async def show_idea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, budget = query.data.split(":")
    context.user_data["budget"] = budget

    idea_text = _pick_idea(context, budget)
    label = BUDGET_LABELS[budget]

    # "Ещё вариант" остаётся в этом же бюджете, "Другой бюджет" — путь назад к выбору
    more_keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Ещё вариант 🔁", callback_data=f"more:{budget}")],
            [InlineKeyboardButton("Другой бюджет 💰", callback_data="rebudget")],
        ]
    )

    await query.edit_message_text(
        f"🎯 *{label}*\n\n{idea_text}",
        parse_mode="Markdown",
        reply_markup=more_keyboard,
    )


# ── вернуться к выбору бюджета ───────────────────────────────────────────────────
async def rebudget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💰 Какой бюджет на компанию?", reply_markup=BUDGET_KEYBOARD)


# ── точка входа ────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("idea", idea_start))
    app.add_handler(CallbackQueryHandler(show_idea, pattern=r"^(budget|more):"))
    app.add_handler(CallbackQueryHandler(rebudget, pattern=r"^rebudget$"))

    logger.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
