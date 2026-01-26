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
from aiogram.enums import ChatAction
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage


# ================== CONFIG ==================
BOT_TOKEN = "8476468855:AAFsZ-gdXPX5k5nnGhxcObjeXLb1g1LZVMo"
ADMIN_ID = 7204477763 # ВСТАВЬ СВОЙ TELEGRAM ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ================== DATABASE ==================
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
    location TEXT,
    views INTEGER DEFAULT 0,
    approved INTEGER DEFAULT 0
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    phone TEXT
)
""")
db.commit()


# ================== MEMORY ==================
feed_index = {}
my_ads_index = {}


# ================== KEYBOARDS ==================
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🍔 Еда"), KeyboardButton(text="📚 Учёба")],
        [KeyboardButton(text="🛠 Услуги")],
        [KeyboardButton(text="📢 Мои объявления")]
    ],
    resize_keyboard=True
)

# Клавиатура для контакта
contact_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
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

admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🗂 Объявления")],
        [KeyboardButton(text="🛂 Модерация")],
        [KeyboardButton(text="⬅️ Назад")]
    ],
    resize_keyboard=True
)


# ================== FSM ==================
class AddFood(StatesGroup):
    photo = State()
    price = State()
    description = State()
    dorm = State()
    location = State()


# ================== START ==================
@dp.message(CommandStart())
async def start(message: Message):
    cursor.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )
    user = cursor.fetchone()

    if not user:
        await message.answer(
            "👋 Добро пожаловать в ГВФ Маркет\n\n"
            "Чтобы другие могли связаться с тобой,\n"
            "поделись контактом 👇",
            reply_markup=contact_keyboard
        )
        return

    await message.answer(
        "👋 Добро пожаловать в ГВФ Маркет\n\n"
        "🍔 Еда из общаг\n"
        "📚 Помощь с учёбой\n"
        "🛠 Разные услуги\n\n"
        "Выбирай, что тебе нужно 👇",
        reply_markup=main_keyboard
    )


# Обработка контакта
@dp.message(lambda m: m.contact is not None)
async def save_contact(message: Message):
    cursor.execute(
        "INSERT OR REPLACE INTO users (user_id, username, phone) VALUES (?, ?, ?)",
        (
            message.from_user.id,
            message.from_user.username,
            message.contact.phone_number
        )
    )
    db.commit()

    await message.answer(
        "✅ Контакт сохранён!\n\n"
        "Теперь ты можешь покупать и продавать 👇",
        reply_markup=main_keyboard
    )


# ================== CANCEL ==================
@dp.message(lambda m: m.text == "❌ Отмена")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено", reply_markup=main_keyboard)


# ================== MENU ==================
@dp.message(lambda m: m.text == "🍔 Еда")
async def food_menu(message: Message):
    await message.answer(
        "🍔 Еда из общаг\n\n"
        "Можно пролистывать и выбирать 👇",
        reply_markup=food_keyboard
    )


@dp.message(lambda m: m.text == "⬅️ Назад")
async def back(message: Message):
    await message.answer("Главное меню", reply_markup=main_keyboard)


@dp.message(lambda m: m.text == "📚 Учёба")
async def study(message: Message):
    await message.answer("📚 Раздел скоро появится 👀")


@dp.message(lambda m: m.text == "🛠 Услуги")
async def services(message: Message):
    await message.answer("🛠 Раздел скоро появится 👀")


# ================== ADD FOOD ==================
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
    await message.answer(
        "🏠 Номер общежития (3, 4 или 5)",
        reply_markup=cancel_keyboard
    )
    await state.set_state(AddFood.dorm)


@dp.message(AddFood.dorm)
async def add_dorm(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) not in [3, 4, 5]:
        await message.answer(
            "❌ Введи номер общежития: 3, 4 или 5",
            reply_markup=cancel_keyboard
        )
        return

    await state.update_data(dorm=int(message.text))
    await message.answer(
        "📍 Этаж и комната\nНапример: 5 этаж, 213",
        reply_markup=cancel_keyboard
    )
    await state.set_state(AddFood.location)


@dp.message(AddFood.location)
async def add_location(message: Message, state: FSMContext):
    data = await state.get_data()

    cursor.execute(
        "INSERT INTO food (user_id, photo, price, description, dorm, location, approved) VALUES (?, ?, ?, ?, ?, ?, 0)",
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

    await bot.send_message(
        ADMIN_ID,
        "🆕 Новое объявление на модерации\n\n"
        f"👤 Пользователь: {message.from_user.id}\n"
        f"🏠 Общага: {data['dorm']}\n"
        f"💰 Цена: {data['price']}"
    )

    await state.clear()
    await message.answer(
        "⏳ Объявление отправлено на модерацию.\n"
        "После проверки оно появится в ленте.",
        reply_markup=main_keyboard
    )


# ================== VIEW FOOD (SWIPE) ==================
@dp.message(lambda m: m.text == "📋 Смотреть еду")
async def view_food(message: Message):
    cursor.execute(
        "SELECT id, user_id, photo, price, description, dorm, location, views FROM food WHERE approved = 1 ORDER BY id DESC"
    )
    foods = cursor.fetchall()

    if not foods:
        await message.answer("📭 Еды пока нет")
        return

    feed_index[message.from_user.id] = 0
    await show_food(message.from_user.id, message)


async def show_food(user_id: int, message: Message):
    cursor.execute(
        "SELECT id, user_id, photo, price, description, dorm, location, views FROM food WHERE approved = 1 ORDER BY id DESC"
    )
    foods = cursor.fetchall()

    index = feed_index.get(user_id, 0)
    if not foods:
        await message.answer("📭 Еды пока нет")
        return

    if index >= len(foods):
        index = 0
        feed_index[user_id] = 0

    food_id, seller_id, photo, price, desc, dorm, loc, views = foods[index]
    total = len(foods)
    current = index + 1

    # increment views
    cursor.execute(
        "UPDATE food SET views = views + 1 WHERE id = ?",
        (food_id,)
    )
    db.commit()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="food_prev"),
                InlineKeyboardButton(text="❤️ Забрать", callback_data=f"like:{food_id}"),
                InlineKeyboardButton(text="➡️ Дальше", callback_data="food_next")
            ]
        ]
    )

    await message.answer_photo(
        photo=photo,
        caption=(
            f"🍔 Еда\n"
            f"📍 {current} / {total}\n\n"
            f"🏠 Общежитие: {dorm}\n"
            f"💰 Цена: {price} ₽\n"
            f"👀 Просмотров: {views+1}\n\n"
            f"📝 Описание:\n{desc}\n\n"
            f"❤️ Нажми, чтобы узнать где забрать"
        ),
        reply_markup=keyboard
    )


@dp.callback_query(lambda c: c.data == "food_next")
async def food_next(callback: CallbackQuery):
    feed_index[callback.from_user.id] += 1

    await callback.message.bot.send_chat_action(
        chat_id=callback.from_user.id,
        action=ChatAction.UPLOAD_PHOTO
    )

    await callback.message.delete()
    await show_food(callback.from_user.id, callback.message)

@dp.callback_query(lambda c: c.data == "food_prev")
async def food_prev(callback: CallbackQuery):
    feed_index[callback.from_user.id] = max(
        0, feed_index.get(callback.from_user.id, 0) - 1
    )

    await callback.message.bot.send_chat_action(
        chat_id=callback.from_user.id,
        action=ChatAction.UPLOAD_PHOTO
    )

    await callback.message.delete()
    await show_food(callback.from_user.id, callback.message)


@dp.callback_query(lambda c: c.data.startswith("like:"))
async def like_food(callback: CallbackQuery):
    food_id = int(callback.data.split(":")[1])

    cursor.execute(
        "SELECT food.user_id, food.dorm, food.location, users.username, users.phone "
        "FROM food JOIN users ON food.user_id = users.user_id "
        "WHERE food.id = ?",
        (food_id,)
    )
    seller_id, dorm, location, username, phone = cursor.fetchone()

    text = (
        "✅ Ты выбрал это объявление\n\n"
        f"🏠 Общежитие: {dorm}\n"
        f"📍 Где забрать:\n{location}\n\n"
        "👤 Продавец:\n"
    )
    if username:
        text += f"👉 <a href='https://t.me/{username}'>Написать в Telegram</a>\n"
    if phone:
        text += f"📱 Телефон: {phone}"

    await callback.answer()
    await callback.message.answer(
        text,
        parse_mode="HTML"
    )


# ================== MY ADS ==================
@dp.message(lambda m: m.text == "📢 Мои объявления")
async def my_ads(message: Message):
    cursor.execute(
        "SELECT id, photo, price, description, dorm, location, views, approved FROM food WHERE user_id = ?",
        (message.from_user.id,)
    )
    ads = cursor.fetchall()

    if not ads:
        await message.answer("📭 У тебя нет объявлений")
        return

    my_ads_index[message.from_user.id] = 0
    await show_my_ad(message.from_user.id, message)


async def show_my_ad(user_id: int, message: Message):
    cursor.execute(
        "SELECT id, photo, price, description, dorm, location, views, approved FROM food WHERE user_id = ?",
        (user_id,)
    )
    ads = cursor.fetchall()

    index = my_ads_index.get(user_id, 0)
    if index >= len(ads):
        index = 0
        my_ads_index[user_id] = 0

    food_id, photo, price, desc, dorm, loc, views, approved = ads[index]
    total = len(ads)
    current = index + 1

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data="my_prev"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete:{food_id}"),
                InlineKeyboardButton(text="➡️", callback_data="my_next")
            ]
        ]
    )

    await message.answer_photo(
        photo=photo,
        caption=(
            f"📢 Моё объявление\n"
            f"📍 {current} / {total}\n\n"
            f"🏠 Общежитие: {dorm}\n"
            f"📍 Место: {loc}\n"
            f"💰 Цена: {price} ₽\n"
            f"👀 Просмотров: {views}\n"
            f"📌 Статус: {'🟢 Активно' if approved else '🟡 На модерации'}\n\n"
            f"📝 Описание:\n{desc}"
        ),
        reply_markup=keyboard
    )
# ================== ADMIN ==================


@dp.callback_query(lambda c: c.data == "my_next")
async def my_next(callback: CallbackQuery):
    my_ads_index[callback.from_user.id] += 1

    await callback.message.bot.send_chat_action(
        chat_id=callback.from_user.id,
        action=ChatAction.UPLOAD_PHOTO
    )

    await callback.message.delete()
    await show_my_ad(callback.from_user.id, callback.message)


@dp.callback_query(lambda c: c.data == "my_prev")
async def my_prev(callback: CallbackQuery):
    my_ads_index[callback.from_user.id] = max(
        0, my_ads_index[callback.from_user.id] - 1
    )

    await callback.message.bot.send_chat_action(
        chat_id=callback.from_user.id,
        action=ChatAction.UPLOAD_PHOTO
    )

    await callback.message.delete()
    await show_my_ad(callback.from_user.id, callback.message)


@dp.callback_query(lambda c: c.data.startswith("delete:"))
async def delete_ad(callback: CallbackQuery):
    food_id = int(callback.data.split(":")[1])

    cursor.execute(
        "DELETE FROM food WHERE id = ? AND user_id = ?",
        (food_id, callback.from_user.id)
    )
    db.commit()

    await callback.message.delete()
    await callback.answer("🗑 Удалено")


# ================== ADMIN ==================
@dp.message(lambda m: m.text == "/admin")
async def admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа")
        return

    await message.answer("🔐 Админка", reply_markup=admin_keyboard)


@dp.message(lambda m: m.text == "📊 Статистика")
async def admin_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT COUNT(*) FROM food")
    food_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM food")
    users = cursor.fetchone()[0]

    await message.answer(
        f"📊 Статистика\n\n"
        f"🍔 Объявлений: {food_count}\n"
        f"👥 Пользователей: {users}"
    )


admin_feed_index = {}

@dp.message(lambda m: m.text == "🗂 Объявления")
async def admin_ads(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    admin_feed_index[message.from_user.id] = 0
    await show_admin_ad(message.from_user.id, message)


async def show_admin_ad(user_id: int, message: Message):
    cursor.execute(
        "SELECT id, photo, price, description, dorm, location FROM food ORDER BY id DESC"
    )
    ads = cursor.fetchall()

    if not ads:
        await message.answer("📭 Объявлений нет")
        return

    index = admin_feed_index.get(user_id, 0)
    if index >= len(ads):
        index = 0
        admin_feed_index[user_id] = 0

    food_id, photo, price, desc, dorm, loc = ads[index]
    total = len(ads)
    current = index + 1

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data="admin_prev"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete:{food_id}"),
                InlineKeyboardButton(text="➡️", callback_data="admin_next")
            ]
        ]
    )

    await message.answer_photo(
        photo=photo,
        caption=(
            f"🆔 ID: {food_id}\n"
            f"📍 {current} / {total}\n\n"
            f"🏠 Общежитие: {dorm}\n"
            f"📍 Место: {loc}\n"
            f"💰 Цена: {price} ₽\n\n"
            f"📝 Описание:\n{desc}"
        ),
        reply_markup=keyboard
    )


@dp.callback_query(lambda c: c.data == "admin_next")
async def admin_next(callback: CallbackQuery):
    await callback.message.bot.send_chat_action(
        chat_id=callback.from_user.id,
        action=ChatAction.UPLOAD_PHOTO
    )
    admin_feed_index[callback.from_user.id] += 1
    await callback.message.delete()
    await show_admin_ad(callback.from_user.id, callback.message)

@dp.callback_query(lambda c: c.data == "admin_prev")
async def admin_prev(callback: CallbackQuery):
    await callback.message.bot.send_chat_action(
        chat_id=callback.from_user.id,
        action=ChatAction.UPLOAD_PHOTO
    )
    admin_feed_index[callback.from_user.id] = max(0, admin_feed_index.get(callback.from_user.id, 0) - 1)
    await callback.message.delete()
    await show_admin_ad(callback.from_user.id, callback.message)

@dp.callback_query(lambda c: c.data.startswith("admin_delete:"))
async def admin_delete(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    food_id = int(callback.data.split(":")[1])
    cursor.execute("DELETE FROM food WHERE id = ?", (food_id,))
    db.commit()

    await callback.answer("🗑 Удалено")
    await callback.message.delete()


# ================== MODERATION ==================
admin_moderation_index = {}

@dp.message(lambda m: m.text == "🛂 Модерация")
async def admin_moderation(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    admin_moderation_index[message.from_user.id] = 0
    await show_moderation(message.from_user.id, message)


async def show_moderation(user_id: int, message: Message):
    cursor.execute(
        "SELECT id, photo, price, description, dorm, location FROM food WHERE approved = 0"
    )
    ads = cursor.fetchall()

    if not ads:
        await message.answer("✅ Нет объявлений на модерации")
        return

    index = admin_moderation_index.get(user_id, 0)
    if index >= len(ads):
        index = 0
        admin_moderation_index[user_id] = 0

    food_id, photo, price, desc, dorm, loc = ads[index]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"mod_reject:{food_id}"),
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"mod_approve:{food_id}")
            ]
        ]
    )

    await message.answer_photo(
        photo=photo,
        caption=(
            f"🆕 На модерации\n\n"
            f"🏠 Общага: {dorm}\n"
            f"📍 {loc}\n"
            f"💰 {price}\n\n"
            f"{desc}"
        ),
        reply_markup=keyboard
    )


@dp.callback_query(lambda c: c.data.startswith("mod_approve:"))
async def mod_approve(callback: CallbackQuery):
    food_id = int(callback.data.split(":")[1])

    cursor.execute(
        "UPDATE food SET approved = 1 WHERE id = ?",
        (food_id,)
    )
    db.commit()

    await callback.answer("✅ Одобрено")
    await callback.message.delete()


@dp.callback_query(lambda c: c.data.startswith("mod_reject:"))
async def mod_reject(callback: CallbackQuery):
    food_id = int(callback.data.split(":")[1])

    cursor.execute(
        "DELETE FROM food WHERE id = ?",
        (food_id,)
    )
    db.commit()

    await callback.answer("❌ Отклонено")
    await callback.message.delete()

# ================== RUN ==================
async def main():
    print("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())