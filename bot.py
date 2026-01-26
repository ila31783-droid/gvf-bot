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
BOT_TOKEN = "8476468855:AAFsZ-gdXPX5k5nnGhxcObjeXLb1g1LZVMo"   # ← ВСТАВЬ ТОКЕН
ADMIN_ID = 7204477763                  # ← ВСТАВЬ СВОЙ TG ID

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
    dorm INTEGER,
    food_type TEXT,
    location TEXT,
    created_at INTEGER
)
""")
db.commit()

# ================= MEMORY =================
user_feed_index = {}
admin_feed_index = {}
user_filters = {}

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
        [KeyboardButton(text="🏠 Фильтр по общаге"), KeyboardButton(text="🍽 Фильтр по типу")],
        [KeyboardButton(text="⬅️ Назад")]
    ],
    resize_keyboard=True
)

filter_dorm_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Общага 3"),
            KeyboardButton(text="Общага 4"),
            KeyboardButton(text="Общага 5")
        ],
        [KeyboardButton(text="❌ Сброс фильтров")],
        [KeyboardButton(text="⬅️ Назад")]
    ],
    resize_keyboard=True
)

filter_type_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="домашнее"), KeyboardButton(text="сладкое")],
        [KeyboardButton(text="полуфабрикаты"), KeyboardButton(text="напитки")],
        [KeyboardButton(text="❌ Сброс фильтров")],
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
    dorm = State()
    food_type = State()
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

# ================= GLOBAL CANCEL =================
@dp.message(lambda m: m.text == "❌ Отмена")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Добавление отменено", reply_markup=main_keyboard)

# ================= START =================
@dp.message(CommandStart())
async def start(message: Message):
    track_user(message.from_user.id)
    await message.answer(
        "👋 Добро пожаловать в ГВФ Маркет 🛒\n\n"
        "Здесь продают еду, напитки и услуги.\n"
        "Выбирай, что нужно 👇",
        reply_markup=main_keyboard
    )


# ================= FOOD MENU =================
@dp.message(lambda m: m.text == "🍔 Еда")
async def food_menu(message: Message):
    await message.answer("🍔 Раздел еды", reply_markup=food_keyboard)

@dp.message(lambda m: m.text == "⬅️ Назад")
async def back(message: Message):
    await message.answer("Главное меню", reply_markup=main_keyboard)

@dp.message(lambda m: m.text == "🏠 Фильтр по общаге")
async def filter_by_dorm(message: Message):
    await message.answer("🏠 Выбери общагу", reply_markup=filter_dorm_keyboard)

@dp.message(lambda m: m.text == "🍽 Фильтр по типу")
async def filter_by_type(message: Message):
    await message.answer("🍽 Выбери тип еды", reply_markup=filter_type_keyboard)

@dp.message(lambda m: m.text.startswith("Общага"))
async def apply_dorm_filter(message: Message):
    dorm = int(message.text.split()[-1])
    if dorm not in [1, 2, 3]:
        return
    user_filters.setdefault(message.from_user.id, {})["dorm"] = dorm
    await message.answer(f"✅ Фильтр: общага {dorm}", reply_markup=food_keyboard)

@dp.message(lambda m: m.text in ["домашнее", "сладкое", "полуфабрикаты", "напитки"])
async def apply_type_filter(message: Message):
    user_filters.setdefault(message.from_user.id, {})["food_type"] = message.text
    await message.answer(f"✅ Фильтр: {message.text}", reply_markup=food_keyboard)

@dp.message(lambda m: m.text == "❌ Сброс фильтров")
async def reset_filters(message: Message):
    user_filters.pop(message.from_user.id, None)
    await message.answer("❌ Фильтры сброшены", reply_markup=food_keyboard)

# ================= ADD FOOD =================
@dp.message(lambda m: m.text == "➕ Добавить еду")
async def add_food(message: Message, state: FSMContext):
    await message.answer("📸 Отправь фото еды", reply_markup=cancel_keyboard)
    await state.set_state(AddFood.photo)

@dp.message(AddFood.photo)
async def food_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer(
            "❌ Нужно отправить именно фото еды 📸",
            reply_markup=cancel_keyboard
        )
        return

    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer(
        "💰 Напиши цену (числом)",
        reply_markup=cancel_keyboard
    )
    await state.set_state(AddFood.price)

@dp.message(AddFood.price)
async def food_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return
    await state.update_data(price=int(message.text))
    await message.answer("📝 Описание", reply_markup=cancel_keyboard)
    await state.set_state(AddFood.description)

@dp.message(AddFood.description)
async def food_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("🏠 Номер общаги (1–3)", reply_markup=cancel_keyboard)
    await state.set_state(AddFood.dorm)

@dp.message(AddFood.dorm)
async def food_dorm(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) not in [3,4,5]:
        return
    await state.update_data(dorm=int(message.text))
    await message.answer(
        "🍽 Тип еды?\n"
        "домашнее / сладкое / полуфабрикаты / напитки",
        reply_markup=cancel_keyboard
    )
    await state.set_state(AddFood.food_type)

@dp.message(AddFood.food_type)
async def food_type(message: Message, state: FSMContext):
    if message.text.lower() not in ["домашнее","сладкое","полуфабрикаты","напитки"]:
        return
    await state.update_data(food_type=message.text.lower())
    await message.answer("📍 Этаж и комната", reply_markup=cancel_keyboard)
    await state.set_state(AddFood.location)

@dp.message(AddFood.location)
async def food_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute(
        "INSERT INTO food VALUES (NULL,?,?,?,?,?,?,?,?)",
        (
            message.from_user.id,
            data["photo"],
            data["price"],
            data["description"],
            data["dorm"],
            data["food_type"],
            message.text,
            now()
        )
    )
    db.commit()
    await state.clear()
    await message.answer("✅ Еда добавлена", reply_markup=main_keyboard)

# ================= VIEW FOOD =================
@dp.message(lambda m: m.text == "📋 Смотреть еду")
async def view_food(message: Message):
    user_feed_index[message.from_user.id] = 0
    await show_food(message.from_user.id, message)

async def show_food(user_id, message):
    filters = user_filters.get(user_id, {})
    query = "SELECT id, photo, price, description, dorm, food_type, location FROM food"
    params = []

    if "dorm" in filters:
        query += " WHERE dorm = ?"
        params.append(filters["dorm"])
    if "food_type" in filters:
        query += " AND food_type = ?" if "WHERE" in query else " WHERE food_type = ?"
        params.append(filters["food_type"])

    query += " ORDER BY created_at DESC"
    cursor.execute(query, params)
    foods = cursor.fetchall()

    index = user_feed_index.get(user_id, 0)
    if index >= len(foods):
        await message.answer("🍽 Еда закончилась", reply_markup=food_keyboard)
        return

    food_id, photo, price, desc, dorm, food_type, loc = foods[index]

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
        caption=f"🏠 Общага {dorm}\n🍽 {food_type}\n💰 {price}\n📝 {desc}",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "next")
async def next_food(callback: CallbackQuery):
    user_feed_index[callback.from_user.id] += 1
    await callback.message.delete()
    await show_food(callback.from_user.id, callback.message)

@dp.callback_query(lambda c: c.data == "prev")
async def prev_food(callback: CallbackQuery):
    user_feed_index[callback.from_user.id] = max(0, user_feed_index[callback.from_user.id] - 1)
    await callback.message.delete()
    await show_food(callback.from_user.id, callback.message)

@dp.callback_query(lambda c: c.data.startswith("like"))
async def like_food(callback: CallbackQuery):
    food_id = int(callback.data.split(":")[1])
    cursor.execute("SELECT location, user_id FROM food WHERE id = ?", (food_id,))
    loc, seller = cursor.fetchone()
    await callback.message.answer(
        f"📍 Где забрать:\n{loc}\n\n"
        f"👤 Продавец:\nhttps://t.me/user?id={seller}"
    )

# ================= RUN =================
async def main():
    print("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())