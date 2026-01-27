import asyncio
import logging
import os
import sqlite3

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("BOT_TOKEN") or "8476468855:AAFsZ-gdXPX5k5nnGhxcObjeXLb1g1LZVMo"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "db")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "database.db")

# ================== DATABASE ==================

db = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    phone TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS food (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    photo TEXT,
    price INTEGER,
    description TEXT,
    dorm INTEGER,
    location TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

db.commit()

# ================== KEYBOARDS ==================

contact_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True
)

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🍔 Еда")],
        [KeyboardButton(text="➕ Добавить еду")],
        [KeyboardButton(text="📢 Мои объявления"), KeyboardButton(text="👤 Профиль")]
    ],
    resize_keyboard=True
)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)

def feed_kb(food_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️", callback_data=f"like:{food_id}"),
                InlineKeyboardButton(text="➡️", callback_data="feed_next")
            ]
        ]
    )

my_food_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Удалить", callback_data="my_delete"),
            InlineKeyboardButton(text="➡️", callback_data="my_next")
        ]
    ]
)

# ================== FSM ==================

class AddFood(StatesGroup):
    photo = State()
    price = State()
    description = State()
    dorm = State()
    location = State()

@router.message(lambda m: m.text == "❌ Отмена")
async def cancel_any(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено", reply_markup=main_keyboard)

# ================== ROUTER ==================

router = Router()
feed_index = {}
current_feed = {}  # user_id -> food_id
my_index = {}

# ---------- START ----------

@router.message(CommandStart())
async def start(message: Message):
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
        (message.from_user.id, message.from_user.username)
    )
    db.commit()

    cursor.execute("SELECT phone FROM users WHERE user_id = ?", (message.from_user.id,))
    phone = cursor.fetchone()[0]

    if phone:
        await message.answer(
            "👋 Добро пожаловать!\n\n⚠️ Бот работает в BETA",
            reply_markup=main_keyboard
        )
    else:
        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Чтобы пользоваться ботом — поделись номером",
            reply_markup=contact_keyboard
        )

# ---------- SAVE CONTACT ----------

@router.message(lambda m: m.contact is not None)
async def save_contact(message: Message):
    cursor.execute(
        "UPDATE users SET phone = ? WHERE user_id = ?",
        (message.contact.phone_number, message.from_user.id)
    )
    db.commit()
    await message.answer("✅ Номер сохранён", reply_markup=main_keyboard)

# ---------- ADD FOOD ----------

@router.message(lambda m: m.text == "➕ Добавить еду")
async def add_food_start(message: Message, state: FSMContext):
    await state.set_state(AddFood.photo)
    await message.answer("📸 Отправь фото еды", reply_markup=cancel_keyboard)

@router.message(AddFood.photo)
async def add_food_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer(
            "❌ Нужно отправить ФОТО еды\nИли нажми ❌ Отмена",
            reply_markup=cancel_keyboard
        )
        return

    await state.update_data(photo=message.photo[-1].file_id)
    await state.set_state(AddFood.price)
    await message.answer("💰 Цена?")

@router.message(AddFood.price)
async def add_food_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Цена числом")
        return
    await state.update_data(price=int(message.text))
    await state.set_state(AddFood.description)
    await message.answer("📝 Описание")

@router.message(AddFood.description)
async def add_food_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AddFood.dorm)
    await message.answer("🏠 Номер общаги (3 / 4 / 5)")

@router.message(AddFood.dorm)
async def add_food_dorm(message: Message, state: FSMContext):
    if message.text not in ["3", "4", "5"]:
        await message.answer("❌ Только 3, 4 или 5")
        return
    await state.update_data(dorm=int(message.text))
    await state.set_state(AddFood.location)
    await message.answer("📍 Этаж и комната")

@router.message(AddFood.location)
async def add_food_finish(message: Message, state: FSMContext):
    data = await state.get_data()

    cursor.execute("""
        INSERT INTO food (user_id, photo, price, description, dorm, location)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        message.from_user.id,
        data["photo"],
        data["price"],
        data["description"],
        data["dorm"],
        message.text
    ))
    db.commit()

    await state.clear()
    await message.answer("✅ Еда добавлена", reply_markup=main_keyboard)

# ---------- VIEW FOOD ----------

@router.message(lambda m: m.text == "🍔 Еда")
async def view_food(message: Message):
    feed_index[message.from_user.id] = 0
    await show_feed(message)

async def show_feed(message: Message):
    cursor.execute(
        "SELECT id, photo, price, description FROM food ORDER BY id DESC"
    )
    foods = cursor.fetchall()

    idx = feed_index.get(message.from_user.id, 0)
    if idx >= len(foods):
        await message.answer("🍽 Больше еды нет")
        return

    food_id, photo, price, desc = foods[idx]
    current_feed[message.from_user.id] = food_id

    await message.answer_photo(
        photo=photo,
        caption=f"💰 {price}\n📝 {desc}",
        reply_markup=feed_kb(food_id)
    )

@router.callback_query(lambda c: c.data == "feed_next")
async def feed_next(callback: CallbackQuery):
    feed_index[callback.from_user.id] = feed_index.get(callback.from_user.id, 0) + 1
    await callback.message.delete()
    await show_feed(callback.message)

# ---------- LIKE + NOTIFY SELLER ----------

@router.callback_query(lambda c: c.data.startswith("like:"))
async def feed_like(callback: CallbackQuery, bot: Bot):
    food_id = int(callback.data.split(":")[1])

    cursor.execute("""
        SELECT f.user_id, f.location
        FROM food f
        WHERE f.id = ?
    """, (food_id,))
    row = cursor.fetchone()

    if not row:
        await callback.answer("Объявление не найдено")
        return

    seller_id, location = row

    # сообщение покупателю
    await callback.message.answer(
        f"📍 Где забрать:\n{location}"
    )

    # уведомление продавцу
    if seller_id != callback.from_user.id:
        await bot.send_message(
            seller_id,
            "❤️ Интерес к объявлению\n\n"
            "Кто-то заинтересовался твоей едой.\n"
            "Зайди в бота и жди сообщения 👀"
        )

    await callback.answer("❤️ Отправлено продавцу")

# ---------- MY ADS ----------

@router.message(lambda m: m.text == "📢 Мои объявления")
async def my_food(message: Message):
    my_index[message.from_user.id] = 0
    await show_my_food(message)

async def show_my_food(message: Message):
    cursor.execute(
        "SELECT id, photo, price, description FROM food WHERE user_id = ? ORDER BY id DESC",
        (message.from_user.id,)
    )
    foods = cursor.fetchall()

    idx = my_index.get(message.from_user.id, 0)

    if not foods:
        await message.answer("📭 У тебя нет объявлений")
        return

    if idx >= len(foods):
        await message.answer("📭 Это все объявления")
        return

    food_id, photo, price, desc = foods[idx]
    await message.answer_photo(
        photo=photo,
        caption=f"💰 {price}\n📝 {desc}",
        reply_markup=my_food_keyboard
    )

@router.callback_query(lambda c: c.data == "my_next")
async def my_next(callback: CallbackQuery):
    my_index[callback.from_user.id] += 1
    await callback.message.delete()
    await show_my_food(callback.message)

@router.callback_query(lambda c: c.data == "my_delete")
async def my_delete(callback: CallbackQuery):
    idx = my_index.get(callback.from_user.id, 0)

    cursor.execute(
        "SELECT id FROM food WHERE user_id = ? ORDER BY id DESC",
        (callback.from_user.id,)
    )
    foods = cursor.fetchall()

    if idx < len(foods):
        cursor.execute("DELETE FROM food WHERE id = ?", (foods[idx][0],))
        db.commit()
        await callback.message.answer("🗑 Объявление удалено")

    await callback.message.delete()
    await show_my_food(callback.message)
    await callback.answer()

# ---------- PROFILE ----------

@router.message(lambda m: m.text == "👤 Профиль")
async def profile(message: Message):
    cursor.execute(
        "SELECT username, phone FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )
    u = cursor.fetchone()

    await message.answer(
        f"👤 Профиль\n\n"
        f"👤 @{u[0]}\n"
        f"📱 {u[1]}"
    )

@router.message()
async def fallback_handler(message: Message):
    await message.answer(
        "⚠️ Я не понял команду.\nИспользуй кнопки ниже 👇",
        reply_markup=main_keyboard
    )

# ================== APP ==================

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    print("✅ BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())