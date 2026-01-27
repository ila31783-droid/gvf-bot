import asyncio
import os
import sqlite3

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN") or "PASTE_BOT_TOKEN"
ADMIN_ID = 7204477763

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "db", "database.db")

TECH_MODE = True  # 🔧 ТЕХРАБОТЫ

# ================= DB =================
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
db = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    phone TEXT
)
""")
db.commit()

# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ================= KEYBOARD =================
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Профиль")],
    ],
    resize_keyboard=True
)

# Клавиатура для запроса контакта
contact_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True
)

# ================= MIDDLEWARE =================
@router.message()
async def tech_mode_guard(message: Message):
    if TECH_MODE and message.from_user.id != ADMIN_ID:
        await message.answer(
            "🔧 Бот временно на технических работах.\n\n"
            "Попробуй зайти чуть позже 🙏"
        )
        return

# ================= START =================
@router.message(Command("start"))
async def start(message: Message):
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
        (message.from_user.id, message.from_user.username)
    )
    db.commit()

    cursor.execute(
        "SELECT phone FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )
    phone = cursor.fetchone()[0]

    if not phone:
        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Чтобы пользоваться ботом, нужно один раз подтвердить номер телефона.",
            reply_markup=contact_keyboard
        )
        return

    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Ты уже зарегистрирован.",
        reply_markup=main_keyboard
    )

# Обработчик получения контакта
@router.message(F.contact)
async def save_contact(message: Message):
    contact = message.contact

    if contact.user_id != message.from_user.id:
        await message.answer("❌ Нужно отправить свой номер")
        return

    cursor.execute(
        "UPDATE users SET phone = ? WHERE user_id = ?",
        (contact.phone_number, message.from_user.id)
    )
    db.commit()

    await message.answer(
        "✅ Номер сохранён. Теперь можно пользоваться ботом.",
        reply_markup=main_keyboard
    )

# ================= PROFILE =================
@router.message(F.text == "👤 Профиль")
async def profile(message: Message):
    cursor.execute(
        "SELECT username, phone FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )
    row = cursor.fetchone()

    if not row:
        await message.answer("❌ Профиль не найден")
        return

    username, phone = row

    await message.answer(
        "👤 Профиль\n\n"
        f"👤 Username: @{username if username else 'не указан'}\n"
        f"📱 Телефон: {phone if phone else 'не указан'}",
        reply_markup=main_keyboard
    )

# ================= RUN =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())