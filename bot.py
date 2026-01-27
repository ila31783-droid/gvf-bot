import asyncio
import os
import logging

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton


router = Router()

APP_VERSION = "step1-2026-01-28a"

# ============ CONFIG (env first) ============
# Put these in Railway Variables / local .env (if you use python-dotenv)
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TECH_MODE = os.getenv("TECH_MODE", "false").strip().lower() in {"1", "true", "yes", "y"}

logging.basicConfig(level=logging.INFO)
railway_env = os.getenv("RAILWAY_ENVIRONMENT", "")
logging.info("[boot] RAILWAY_ENVIRONMENT=%r", railway_env)
logging.info("[boot] APP_VERSION=%s", APP_VERSION)
logging.info("[boot] BOT_TOKEN present key=%s len=%d", "BOT_TOKEN" in os.environ, len(os.getenv("BOT_TOKEN", "")))
logging.info(
    "[boot] env keys (filtered)=%s",
    sorted(
        {
            k
            for k in os.environ.keys()
            if "TOKEN" in k or k in {"BOT_TOKEN", "ADMIN_ID", "TECH_MODE"}
        }
    ),
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is empty. Set BOT_TOKEN environment variable.")

# ADMIN_ID can be 0 during early dev; TECH_MODE guard will only apply when ADMIN_ID is set.

# ============ KEYBOARDS ============

def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍔 Еда"), KeyboardButton(text="📚 Учёба")],
            [KeyboardButton(text="🛠 Услуги"), KeyboardButton(text="📢 Мои объявления")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )

# ============ HANDLERS ============

@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "👋 Привет! Это студенческий маркет-бот.\n\n"
        "Пока что включён *Шаг 1*: каркас, меню и команды.\n"
        "Дальше добавим регистрацию, объявления и модерацию.",
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )


@router.message(Command("help"))
@router.message(F.text == "ℹ️ Помощь")
async def help_cmd(message: Message):
    await message.answer(
        "Команды:\n"
        "/start — главное меню\n"
        "/help — помощь\n\n"
        "Разделы скоро будут активны: Еда, Учёба, Услуги, Мои объявления.",
        reply_markup=main_kb(),
    )


@router.message()
async def tech_guard(message: Message):
    """If TECH_MODE=true, block all non-admin messages except commands/contact."""
    # Skip contacts and any /commands
    if message.contact:
        return
    if message.text and message.text.startswith("/"):
        return

    if not TECH_MODE:
        return

    # If admin id isn't configured, we just block everyone (safe default in tech mode)
    if ADMIN_ID and message.from_user.id == ADMIN_ID:
        return

    await message.answer(
        "🛠 Бот на технических работах.\n"
        "Скоро вернёмся — спасибо за терпение 🙏"
    )


@router.message(F.text.in_({"🍔 Еда", "📚 Учёба", "🛠 Услуги", "📢 Мои объявления"}))
async def stub_sections(message: Message):
    await message.answer(
        "Этот раздел будет подключён на следующих шагах.\n"
        "Сейчас работает только каркас (Шаг 1).",
        reply_markup=main_kb(),
    )


# ============ APP ENTRYPOINT ============

async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # NOTE: Drop pending updates to avoid processing old messages after redeploy.
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())