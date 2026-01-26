import asyncio
import sqlite3

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
from aiogram.fsm.storage.memory import MemoryStorage

# ================= TOKEN =================
BOT_TOKEN = "ВСТАВЬ_СВОЙ_ТОКЕН"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================= DATABASE =================
db = sqlite3.connect("database.db")
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS food (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    photo TEXT,
    price TEXT,
    description TEXT,
    dorm INTEGER,
    location TEXT
)
""")
db.commit()

# ================= KEYBOARDS =================
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🍔 Еда")],
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
    dorm = State()
    location = State()

# ================= START =================
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "👋 Добро пожаловать в ГВФ Маркет\n\n"
        "Здесь продают еду из общаги\n\n"
        "Выбирай действие 👇",
        reply_markup=main_keyboard
    )

# ================= CANCEL =================
@dp.message(lambda m: m.text == "❌ Отмена")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено", reply_markup=main_keyboard)

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
async def add_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Нужно отправить фото", reply_markup=cancel_keyboard)
        return

    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("💰 Напиши цену", reply_markup=cancel_keyboard)
    await state.set_state(AddFood.price)

@dp.message(AddFood.price)
async def add_price(message: Message, state: FSMContext):
    await state.update_data(price=message.text)
    await message.answer("📝 Напиши описание", reply_markup=cancel_keyboard)
    await state.set_state(AddFood.description)

@dp.message(AddFood.description)
async def add_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("🏠 Номер общаги (3, 4 или 5)", reply_markup=cancel_keyboard)
    await state.set_state(AddFood.dorm)

@dp.message(AddFood.dorm)
async def add_dorm(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) not in [3, 4, 5]:
        await message.answer("❌ Введи 3, 4 или 5", reply_markup=cancel_keyboard)
        return

    await state.update_data(dorm=int(message.text))
    await message.answer("📍 Этаж и комната\nНапример: 5 этаж 213", reply_markup=cancel_keyboard)
    await state.set_state(AddFood.location)

@dp.message(AddFood.location)
async def add_location(message: Message, state: FSMContext):
    data = await state.get_data()

    cursor.execute(
        "INSERT INTO food (user_id, photo, price, description, dorm, location) VALUES (?, ?, ?, ?, ?, ?)",
        (
            message.from_user.id,
            data["photo"],
            data["price"],
            data["description"],
            data["dorm"],
            message.text
        )
    )
    db.commit()

    await state.clear()
    await message.answer("✅ Еда добавлена", reply_markup=main_keyboard)

# ================= VIEW FOOD =================
@dp.message(lambda m: m.text == "📋 Смотреть еду")
async def view_food(message: Message):
    cursor.execute("SELECT photo, price, description, dorm, location FROM food ORDER BY id DESC")
    foods = cursor.fetchall()

    if not foods:
        await message.answer("📭 Еды пока нет")
        return

    for food_id, photo, price, desc, dorm, loc in cursor.execute(
        "SELECT id, photo, price, description, dorm, location FROM food ORDER BY id DESC"
    ):
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✉️ Написать продавцу",
                        url=f"https://t.me/{message.from_user.username}"
                    )
                ]
            ]
        )

        await message.answer_photo(
            photo=photo,
            caption=f"🏠 Общага {dorm}\n💰 {price}\n📝 {desc}\n📍 {loc}",
            reply_markup=keyboard
        )

# ================= MY ADS =================
@dp.message(lambda m: m.text == "📢 Мои объявления")
async def my_ads(message: Message):
    cursor.execute(
        "SELECT id, photo, price, description, dorm, location FROM food WHERE user_id = ?",
        (message.from_user.id,)
    )
    ads = cursor.fetchall()

    if not ads:
        await message.answer("📭 У тебя нет объявлений")
        return

    for food_id, photo, price, desc, dorm, loc in ads:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗑 Удалить",
                        callback_data=f"delete:{food_id}"
                    )
                ]
            ]
        )

        await message.answer_photo(
            photo=photo,
            caption=f"🏠 Общага {dorm}\n💰 {price}\n📝 {desc}\n📍 {loc}",
            reply_markup=keyboard
        )

# ================= DELETE HANDLER =================
@dp.callback_query(lambda c: c.data.startswith("delete:"))
async def delete_food(callback: CallbackQuery):
    food_id = int(callback.data.split(":")[1])

    cursor.execute(
        "DELETE FROM food WHERE id = ? AND user_id = ?",
        (food_id, callback.from_user.id)
    )
    db.commit()

    await callback.message.delete()
    await callback.answer("🗑 Удалено")

# ================= RUN =================
async def main():
    print("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())