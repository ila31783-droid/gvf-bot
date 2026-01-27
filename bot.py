import os

BOT_TOKEN = os.getenv("BOT_TOKEN") or "ВСТАВЬ_ТОКЕН"
ADMIN_ID = 7204477763  # твой TG ID

MAINTENANCE = True          # режим техработ
ADMIN_VIEW_AS_USER = False  # админ как обычный пользователь
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "db", "database.db")

db = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = db.cursor()
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🍔 Еда из общаг")],
        [KeyboardButton(text="📦 Барахолка")],
        [KeyboardButton(text="📢 Мои объявления")],
        [KeyboardButton(text="👤 Профиль")]
    ],
    resize_keyboard=True
)

contact_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

profile_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Обновить контакт")],
        [KeyboardButton(text="⬅️ Назад")]
    ],
    resize_keyboard=True
)from aiogram import Router
from aiogram.types import Message
from aiogram.exceptions import SkipHandler
from config import MAINTENANCE, ADMIN_ID, ADMIN_VIEW_AS_USER

router = Router()

@router.message()
async def maintenance_guard(message: Message):
    if not MAINTENANCE:
        raise SkipHandler

    if message.from_user.id == ADMIN_ID and not ADMIN_VIEW_AS_USER:
        raise SkipHandler

    await message.answer(
        "🛠 Ведутся технические работы\n\n"
        "Бот временно недоступен.\n"
        "Скоро всё заработает 🙏"
    )from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from db import cursor, db
from keyboards import main_keyboard, contact_keyboard
import time

router = Router()

@router.message(CommandStart())
async def start(message: Message):
    cursor.execute(
        "SELECT phone FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            "INSERT INTO users (user_id, username, first_seen) VALUES (?, ?, ?)",
            (message.from_user.id, message.from_user.username, int(time.time()))
        )
        db.commit()

        await message.answer(
            "⚠️ Бот в BETA\n\n"
            "Чтобы пользоваться ботом, нужно поделиться контактом 📱",
            reply_markup=contact_keyboard
        )
        return

    if not row[0]:
        await message.answer(
            "⚠️ Нужно поделиться контактом 📱",
            reply_markup=contact_keyboard
        )
        return

    await message.answer(
        "👋 Добро пожаловать в GVF Market",
        reply_markup=main_keyboard
    )


@router.message(F.contact)
async def save_contact(message: Message):
    cursor.execute(
        "UPDATE users SET phone = ?, username = ? WHERE user_id = ?",
        (message.contact.phone_number, message.from_user.username, message.from_user.id)
    )
    db.commit()

    await message.answer(
        "✅ Контакт сохранён!",
        reply_markup=main_keyboard
    )
    from aiogram import Router
from aiogram.types import Message
from db import cursor
from keyboards import profile_keyboard, main_keyboard

router = Router()

@router.message(lambda m: m.text == "👤 Профиль")
async def profile(message: Message):
    cursor.execute(
        "SELECT username, phone FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )
    user = cursor.fetchone()

    username = f"@{user[0]}" if user and user[0] else "не указан"
    phone = user[1] if user and user[1] else "не привязан"

    await message.answer(
        f"👤 Твой профиль\n\n"
        f"🆔 ID: {message.from_user.id}\n"
        f"👤 Username: {username}\n"
        f"📱 Телефон: {phone}",
        reply_markup=profile_keyboard
    )


@router.message(lambda m: m.text == "⬅️ Назад")
async def back(message: Message):
    await message.answer("Главное меню", reply_markup=main_keyboard)
    import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from routers import start, profile, maintenance

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Порядок ВАЖЕН
    dp.include_router(maintenance.router)
    dp.include_router(start.router)
    dp.include_router(profile.router)

    print("✅ BOT STARTED (clean core)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())