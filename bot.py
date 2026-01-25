import asyncio
import sqlite3
import time

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# ================= CONFIG =================
BOT_TOKEN = "8476468855:AAFsZ-gdXPX5k5nnGhxcObjeXLb1g1LZVMo"
ADMIN_ID = 7204477763  # ← ВСТАВЬ СВОЙ TG ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================= DATABASE =================
db = sqlite3.connect("database.db")
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    last_active INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS food (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    photo TEXT,
    price INTEGER,
    description TEXT,
    location TEXT,
    created_at INTEGER
)
""")

db.commit()

# ================= MEMORY =================
user_feed_index = {}
admin_feed_index = {}

# ================= KEYBOARDS =================
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🍔 Еда"), KeyboardButton(text="📚 Учёба")],
        [KeyboardButton(text="🛠 Услуги")],
        [KeyboardButton(text="📢 Мои объявления")]
    ],
    resize_keyboard=True
)

food_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить еду")],
        [KeyboardButton(text="📋 Смотреть еду")],
        [KeyboardButton(text="⬅️ Назад")]
    ],
    resize_keyboard=True
)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)

# ================= FSM =================
class AddFood(StatesGroup):
    photo = State()
    price = State()
    description = State()
    location = State()

# ================= HELPERS =================
def now():
    return int(time.time())

def track_user(user_id: int):
    cursor.execute(
        "INSERT OR REPLACE INTO users (user_id, last_active) VALUES (?, ?)",
        (user_id, now())
    )
    db.commit()

# ================= START =================
@dp.message(CommandStart())
async def start(message: Message):
    user_id = message.from_user.id

    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    is_new = cursor.fetchone() is None

    track_user(user_id)

    if is_new:
        text = (
            "👋 Добро пожаловать!\n\n"
            "Это бот «ГВФ Маркет» 🛒\n"
            "Здесь производится продажа еды, товаров повседневного спроса,\n"
            "а также различных услуг в сфере учёбы 📚\n\n"
            "👇 Выбирай, что тебе нужно"
        )
    else:
        text = "👋 С возвращением!\nВыбирай раздел 👇"

    await message.answer(text, reply_markup=main_keyboard)

# ================= FOOD MENU =================
@dp.message(lambda m: m.text == "🍔 Еда")
async def food_menu(message: Message):
    await message.answer("🍔 Раздел еды", reply_markup=food_keyboard)

@dp.message(lambda m: m.text == "⬅️ Назад")
async def back(message: Message):
    await message.answer("Главное меню", reply_markup=main_keyboard)

# ================= ADD FOOD =================
@dp.message(lambda m: m.text == "➕ Добавить еду")
async def add_food(message: Message, state: FSMContext):
    await message.answer("📸 Отправь фото еды", reply_markup=cancel_keyboard)
    await state.set_state(AddFood.photo)

@dp.message(AddFood.photo)
async def food_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Нужно фото", reply_markup=cancel_keyboard)
        return
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("💰 Цена?", reply_markup=cancel_keyboard)
    await state.set_state(AddFood.price)

@dp.message(AddFood.price)
async def food_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Цена числом", reply_markup=cancel_keyboard)
        return
    await state.update_data(price=int(message.text))
    await message.answer("📝 Описание", reply_markup=cancel_keyboard)
    await state.set_state(AddFood.description)

@dp.message(AddFood.description)
async def food_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("📍 Общежитие / этаж / комната", reply_markup=cancel_keyboard)
    await state.set_state(AddFood.location)

@dp.message(AddFood.location)
async def food_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute(
        "INSERT INTO food (user_id, photo, price, description, location, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (message.from_user.id, data["photo"], data["price"], data["description"], message.text, now())
    )
    db.commit()
    await state.clear()
    await message.answer("✅ Еда добавлена", reply_markup=main_keyboard)

# ================= VIEW FOOD (SWIPE) =================
@dp.message(lambda m: m.text == "📋 Смотреть еду")
async def view_food(message: Message):
    user_feed_index[message.from_user.id] = 0
    await show_food(message.from_user.id, message)

async def show_food(user_id: int, message: Message):
    cursor.execute("SELECT id, photo, price, description, location FROM food ORDER BY created_at DESC")
    foods = cursor.fetchall()

    index = user_feed_index.get(user_id, 0)
    if index >= len(foods):
        await message.answer("🍽 Еда закончилась", reply_markup=food_keyboard)
        return

    food_id, photo, price, description, location = foods[index]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data="prev"),
                InlineKeyboardButton(text="❤️", callback_data=f"like:{food_id}"),
                InlineKeyboardButton(text="➡️", callback_data="next")
            ]
        ]
    )

    await message.answer_photo(
        photo=photo,
        caption=f"💰 {price}\n📝 {description}",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "next")
async def next_food(callback: CallbackQuery):
    await callback.answer()
    user_feed_index[callback.from_user.id] += 1
    await callback.message.delete()
    await show_food(callback.from_user.id, callback.message)

@dp.callback_query(lambda c: c.data == "prev")
async def prev_food(callback: CallbackQuery):
    await callback.answer()
    user_feed_index[callback.from_user.id] = max(0, user_feed_index[callback.from_user.id] - 1)
    await callback.message.delete()
    await show_food(callback.from_user.id, callback.message)

@dp.callback_query(lambda c: c.data.startswith("like"))
async def like_food(callback: CallbackQuery):
    await callback.answer()
    food_id = int(callback.data.split(":")[1])
    cursor.execute("SELECT location FROM food WHERE id = ?", (food_id,))
    loc = cursor.fetchone()
    await callback.message.answer(f"📍 Где забрать:\n{loc[0]}")

# ================= ADMIN =================
@dp.message(lambda m: m.text == "/admin" and m.from_user.id == ADMIN_ID)
async def admin_panel(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🍔 Все объявления", callback_data="admin_food")],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]
        ]
    )
    await message.answer("👑 Админка", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "admin_stats" and c.from_user.id == ADMIN_ID)
async def admin_stats(callback: CallbackQuery):
    await callback.answer()
    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM food")
    foods = cursor.fetchone()[0]
    await callback.message.answer(
        f"📊 Статистика\n\n"
        f"👤 Пользователей: {users}\n"
        f"🍔 Объявлений: {foods}"
    )

@dp.callback_query(lambda c: c.data == "admin_food" and c.from_user.id == ADMIN_ID)
async def admin_food(callback: CallbackQuery):
    await callback.answer()
    admin_feed_index[callback.from_user.id] = 0
    await show_admin_food(callback)

async def show_admin_food(callback: CallbackQuery):
    cursor.execute("SELECT id, photo, price, description, location FROM food ORDER BY created_at DESC")
    foods = cursor.fetchall()

    index = admin_feed_index.get(callback.from_user.id, 0)
    if index >= len(foods):
        await callback.message.answer("Нет объявлений")
        return

    food_id, photo, price, desc, loc = foods[index]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data="admin_prev"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete:{food_id}"),
                InlineKeyboardButton(text="➡️", callback_data="admin_next")
            ]
        ]
    )

    await callback.message.answer_photo(
        photo=photo,
        caption=f"💰 {price}\n📝 {desc}\n📍 {loc}",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "admin_next" and c.from_user.id == ADMIN_ID)
async def admin_next(callback: CallbackQuery):
    await callback.answer()
    admin_feed_index[callback.from_user.id] += 1
    await show_admin_food(callback)

@dp.callback_query(lambda c: c.data == "admin_prev" and c.from_user.id == ADMIN_ID)
async def admin_prev(callback: CallbackQuery):
    await callback.answer()
    admin_feed_index[callback.from_user.id] = max(0, admin_feed_index[callback.from_user.id] - 1)
    await show_admin_food(callback)

@dp.callback_query(lambda c: c.data.startswith("admin_delete") and c.from_user.id == ADMIN_ID)
async def admin_delete(callback: CallbackQuery):
    await callback.answer()
    food_id = int(callback.data.split(":")[1])
    cursor.execute("DELETE FROM food WHERE id = ?", (food_id,))
    db.commit()
    await callback.message.answer("🗑 Объявление удалено")

@dp.callback_query(lambda c: c.data == "admin_close" and c.from_user.id == ADMIN_ID)
async def admin_close(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()

# ================= RUN =================
async def main():
    print("БОТ ЗАПУЩЕН")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())