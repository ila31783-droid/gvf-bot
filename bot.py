import asyncio

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

# ================= TOKEN =================
BOT_TOKEN = "8476468855:AAFsZ-gdXPX5k5nnGhxcObjeXLb1g1LZVMo"

# ================= BOT =================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================= HANDLERS =================
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Бот жив 🚀")

# ================= RUN =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


# ================= DATABASE =================
db = sqlite3.connect("database.db")
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS food (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    photo TEXT,
    price INTEGER,
    description TEXT,
    location TEXT
)
""")
db.commit()

# ================= MEMORY =================
user_feed_index = {}

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
    keyboard=[
        [KeyboardButton(text="❌ Отмена")]
    ],
    resize_keyboard=True
)

# ================= FSM =================
class AddFood(StatesGroup):
    photo = State()
    price = State()
    description = State()
    location = State()

# ================= START =================
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Привет 👋\n\nЭто маркетплейс ГВФ",
        reply_markup=main_keyboard
    )

# ================= GLOBAL CANCEL =================
@dp.message(lambda m: m.text == "❌ Отмена")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено", reply_markup=main_keyboard)

# ================= FOOD =================
@dp.message(lambda m: m.text == "🍔 Еда")
async def food_menu(message: Message):
    await message.answer("🍔 Раздел еды", reply_markup=food_keyboard)

@dp.message(lambda m: m.text == "➕ Добавить еду")
async def add_food(message: Message, state: FSMContext):
    await message.answer(
        "📸 Отправь фото еды\n\nЕсли передумал — нажми ❌ Отмена",
        reply_markup=cancel_keyboard
    )
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
    await state.update_data(price=message.text)
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
        "INSERT INTO food (user_id, photo, price, description, location) VALUES (?, ?, ?, ?, ?)",
        (message.from_user.id, data["photo"], data["price"], data["description"], message.text)
    )
    db.commit()
    await message.answer("✅ Еда добавлена", reply_markup=main_keyboard)
    await state.clear()

# ================= VIEW FOOD (ARROWS) =================
@dp.message(lambda m: m.text == "📋 Смотреть еду")
async def view_food(message: Message):
    user_feed_index[message.from_user.id] = 0
    await show_food(message.from_user.id, message)

@dp.message(lambda m: m.text == "⬅️ Назад")
async def back_to_main(message: Message):
    await message.answer("Главное меню 👇", reply_markup=main_keyboard)

async def show_food(user_id: int, message: Message):
    cursor.execute("SELECT id, photo, price, description, location FROM food ORDER BY id DESC")
    foods = cursor.fetchall()

    if not foods:
        await message.answer("📭 Пока нет еды")
        return

    index = user_feed_index.get(user_id, 0)

    if index < 0:
        index = 0
    if index >= len(foods):
        index = len(foods) - 1

    user_feed_index[user_id] = index

    food_id, photo, price, description, location = foods[index]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data="prev"),
                InlineKeyboardButton(text="❤️", callback_data=f"like:{food_id}"),
                InlineKeyboardButton(text="👎", callback_data="next"),
                InlineKeyboardButton(text="➡️", callback_data="next")
            ]
        ]
    )

    await message.answer_photo(
        photo=photo,
        caption=f"🍔 {index + 1} / {len(foods)}\n\n💰 {price}\n📝 {description}",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "next")
async def next_food(callback: CallbackQuery):
    user_feed_index[callback.from_user.id] += 1
    await callback.message.delete()
    await show_food(callback.from_user.id, callback.message)

@dp.callback_query(lambda c: c.data == "prev")
async def prev_food(callback: CallbackQuery):
    if user_feed_index.get(callback.from_user.id, 0) > 0:
        user_feed_index[callback.from_user.id] -= 1
    await callback.message.delete()
    await show_food(callback.from_user.id, callback.message)

@dp.callback_query(lambda c: c.data.startswith("like"))
async def like_food(callback: CallbackQuery):
    food_id = int(callback.data.split(":")[1])
    cursor.execute("SELECT location FROM food WHERE id = ?", (food_id,))
    location = cursor.fetchone()
    await callback.answer()
    await callback.message.answer(f"📍 Где забрать:\n{location[0]}")

# ================= MY ADS =================
@dp.message(lambda m: m.text == "📢 Мои объявления")
async def my_ads(message: Message):
    cursor.execute(
        "SELECT id, photo, price, description, location FROM food WHERE user_id = ?",
        (message.from_user.id,)
    )
    foods = cursor.fetchall()

    if not foods:
        await message.answer("📭 У тебя нет объявлений")
        return

    for food_id, photo, price, desc, loc in foods:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete:{food_id}")]
            ]
        )
        await message.answer_photo(
            photo=photo,
            caption=f"💰 {price}\n📝 {desc}\n📍 {loc}",
            reply_markup=keyboard
        )

@dp.callback_query(lambda c: c.data.startswith("delete"))
async def delete_food(callback: CallbackQuery):
    food_id = int(callback.data.split(":")[1])
    cursor.execute("DELETE FROM food WHERE id = ?", (food_id,))
    db.commit()
    await callback.message.delete()
    await callback.answer("🗑 Удалено")

# ================= OTHER =================
@dp.message(lambda m: m.text == "📚 Учёба")
async def study(message: Message):
    await message.answer("📚 Скоро")

@dp.message(lambda m: m.text == "🛠 Услуги")
async def services(message: Message):
    await message.answer("🛠 Скоро")

# ================= RUN =================
async def main():
    print("БОТ ЗАПУЩЕН")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
