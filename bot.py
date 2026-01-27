import asyncio
import logging
import os
from typing import Any, Optional

import asyncpg
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup


router = Router()

APP_VERSION = "step2-2026-01-28a"

# ============ CONFIG (env first) ============
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TECH_MODE = os.getenv("TECH_MODE", "false").strip().lower() in {"1", "true", "yes", "y"}

DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or os.getenv("DATABASE_PUBLIC_URL", "").strip()

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
            if "TOKEN" in k or k in {"BOT_TOKEN", "ADMIN_ID", "TECH_MODE", "DATABASE_URL", "DATABASE_PUBLIC_URL"}
        }
    ),
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is empty. Set BOT_TOKEN environment variable.")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is empty. Add Postgres and connect it to this service so DATABASE_URL is available."
    )

# ============ DB (asyncpg) ============

_pool: Optional[asyncpg.Pool] = None


async def db_init() -> None:
    """Create pool and ensure tables exist."""
    global _pool

    # asyncpg accepts postgres:// and postgresql://
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)

    async with _pool.acquire() as conn:
        # Users: store phone verification so it survives redeploys
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              user_id   BIGINT PRIMARY KEY,
              username  TEXT,
              phone     TEXT,
              is_verified BOOLEAN NOT NULL DEFAULT FALSE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # Ads table placeholder (we will fill it on later steps)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ads (
              id        BIGSERIAL PRIMARY KEY,
              user_id   BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
              category  TEXT NOT NULL,
              photo_file_id TEXT,
              price     TEXT,
              description TEXT,
              approved  BOOLEAN NOT NULL DEFAULT FALSE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

    logging.info("[db] initialized pool and ensured tables")


def db_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool


async def db_get_user(user_id: int) -> Optional[asyncpg.Record]:
    async with db_pool().acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)


async def db_upsert_user(user_id: int, username: Optional[str]) -> None:
    async with db_pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users(user_id, username)
            VALUES($1, $2)
            ON CONFLICT (user_id)
            DO UPDATE SET username=EXCLUDED.username, updated_at=NOW();
            """,
            user_id,
            username,
        )


async def db_set_phone_verified(user_id: int, username: Optional[str], phone: str) -> None:
    async with db_pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users(user_id, username, phone, is_verified)
            VALUES($1, $2, $3, TRUE)
            ON CONFLICT (user_id)
            DO UPDATE SET username=EXCLUDED.username,
                          phone=EXCLUDED.phone,
                          is_verified=TRUE,
                          updated_at=NOW();
            """,
            user_id,
            username,
            phone,
        )


# ============ KEYBOARDS ============

def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍔 Еда"), KeyboardButton(text="📚 Учёба")],
            [KeyboardButton(text="🛠 Услуги"), KeyboardButton(text="📢 Мои объявления")],
            [KeyboardButton(text="📱 Обновить контакт"), KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


def contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ============ HANDLERS ============

@router.message(CommandStart())
async def start(message: Message):
    # Ensure user exists
    await db_upsert_user(message.from_user.id, message.from_user.username)

    user = await db_get_user(message.from_user.id)
    verified = bool(user and user.get("is_verified"))

    if not verified:
        await message.answer(
            "👋 Привет! Чтобы пользоваться ботом, подтвердите номер: \n\n"
            "Нажми кнопку ниже и отправь свой контакт 👇",
            reply_markup=contact_kb(),
        )
        return

    await message.answer(
        "✅ Номер подтверждён!\n\n"
        "Выбирай раздел в меню 👇",
        reply_markup=main_kb(),
    )


@router.message(Command("help"))
@router.message(F.text == "ℹ️ Помощь")
async def help_cmd(message: Message):
    await message.answer(
        "Команды:\n"
        "/start — главное меню\n"
        "/help — помощь\n\n"
        "Если бот просит подтвердить номер — нажми ‘📱 Поделиться контактом’.",
        reply_markup=main_kb(),
    )


@router.message(F.contact)
async def on_contact(message: Message):
    # Security: accept only own contact
    if not message.contact or message.contact.user_id != message.from_user.id:
        await message.answer("⚠️ Отправь *свой* контакт через кнопку ниже.", reply_markup=contact_kb(), parse_mode="Markdown")
        return

    phone = (message.contact.phone_number or "").strip()
    if not phone:
        await message.answer("⚠️ Не удалось прочитать номер. Попробуй ещё раз.", reply_markup=contact_kb())
        return

    await db_set_phone_verified(message.from_user.id, message.from_user.username, phone)

    await message.answer(
        "✅ Спасибо! Номер подтверждён.\n\nТеперь ты можешь пользоваться ботом 👇",
        reply_markup=main_kb(),
    )


@router.message(F.text == "📱 Обновить контакт")
async def update_contact(message: Message):
    await message.answer(
        "Ок! Нажми кнопку и отправь контакт ещё раз 👇",
        reply_markup=contact_kb(),
    )


@router.message()
async def tech_guard_and_stubs(message: Message):
    """TECH_MODE gate + stubs for sections (Step 2)."""

    # Skip contacts and any /commands
    if message.contact:
        return
    if message.text and message.text.startswith("/"):
        return

    # If user isn't verified, keep asking for contact
    user = await db_get_user(message.from_user.id)
    verified = bool(user and user.get("is_verified"))
    if not verified:
        await message.answer(
            "Чтобы пользоваться ботом, подтвердите номер 👇",
            reply_markup=contact_kb(),
        )
        return

    if TECH_MODE:
        if ADMIN_ID and message.from_user.id == ADMIN_ID:
            return
        await message.answer(
            "🛠 Бот на технических работах.\n"
            "Скоро вернёмся — спасибо за терпение 🙏"
        )
        return

    # Stubs for sections
    if message.text in {"🍔 Еда", "📚 Учёба", "🛠 Услуги", "📢 Мои объявления"}:
        await message.answer(
            "Этот раздел будет подключён на следующих шагах.\n"
            "Сейчас работает регистрация и сохранение данных в Postgres ✅",
            reply_markup=main_kb(),
        )
        return

    await message.answer("Не понял 😅 Нажми кнопку в меню или напиши /help", reply_markup=main_kb())


# ============ APP ENTRYPOINT ============

async def main() -> None:
    await db_init()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # Drop pending updates to avoid processing old messages after redeploy.
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())