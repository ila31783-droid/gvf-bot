import asyncio
import sqlite3
import os

from aiogram import Bot, Dispatcher
from aiogram import F
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


# ================== CONFIG ==================
BOT_TOKEN = "8476468855:AAFsZ-gdXPX5k5nnGhxcObjeXLb1g1LZVMo"
ADMIN_ID = 7204477763 # ВСТАВЬ СВОЙ TELEGRAM ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ================== DATABASE ==================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

db = sqlite3.connect(DB_PATH)
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
    views INTEGER DEFAULT 0
)
""")
# === CREATE items TABLE after food ===
cursor.execute("""
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    photo TEXT,
    price TEXT,
    description TEXT,
    dorm INTEGER,
    location TEXT,
    views INTEGER DEFAULT 0,
    approved INTEGER DEFAULT 1
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    phone TEXT,
    first_seen INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS views (
    user_id INTEGER,
    food_id INTEGER,
    UNIQUE(user_id, food_id)
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS likes (
    food_id INTEGER,
    buyer_id INTEGER,
    seller_id INTEGER,
    created_at INTEGER
)
""")
db.commit()


# ================== CONTACT CHECK ==================
async def require_contact(message: Message) -> bool:
    cursor.execute(
        "SELECT phone FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )
    row = cursor.fetchone()

    if not row or not row[0]:
        await message.answer(
            "⚠️ Чтобы пользоваться ботом, нужно поделиться контактом 📱",
            reply_markup=contact_keyboard
        )
        return False

    return True

# ================== MEMORY ==================
feed_index = {}
my_ads_index = {}
items_feed_index = {}
my_items_index = {}
admin_items_index = {}


# ================== KEYBOARDS ==================
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🍔 Еда из общаг")],
        [KeyboardButton(text="📦 Барахолка")],
        [KeyboardButton(text="📚 Учёба (скоро)")],
        [KeyboardButton(text="📢 Мои объявления")],
        [KeyboardButton(text="👤 Профиль")]
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

# Клавиатура раздела вещей
items_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить вещь")],
        [KeyboardButton(text="📋 Смотреть вещи")],
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
        [KeyboardButton(text="📣 Рассылка")],
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

# FSM для добавления вещей (барахолка)
class AddItem(StatesGroup):
    photo = State()
    price = State()
    description = State()
    dorm = State()
    location = State()




# ================== BROADCAST FSM ==================
class Broadcast(StatesGroup):
    text = State()


# ================== START ==================
@dp.message(CommandStart())
async def start(message: Message):
    cursor.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )
    exists = cursor.fetchone()

    if not exists:
        cursor.execute(
            "INSERT INTO users (user_id, username, first_seen) VALUES (?, ?, ?)",
            (
                message.from_user.id,
                message.from_user.username,
                int(asyncio.get_event_loop().time())
            )
        )
        db.commit()
        await message.answer(
            "⚠️ Бот в BETA\n\n"
            "Для работы бота ОБЯЗАТЕЛЬНО нужно поделиться контактом 📱\n"
            "Без этого покупатели и продавцы не смогут связаться друг с другом.",
            reply_markup=contact_keyboard
        )
        return

    cursor.execute(
        "SELECT phone FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )
    phone = cursor.fetchone()

    if not phone or not phone[0]:
        await message.answer(
            "⚠️ Для работы бота нужно поделиться контактом 📱",
            reply_markup=contact_keyboard
        )
        return


# Обработка контакта
@dp.message(F.contact)
async def save_contact(message: Message):
    cursor.execute(
        "UPDATE users SET phone = ?, username = ? WHERE user_id = ?",
        (
            message.contact.phone_number,
            message.from_user.username,
            message.from_user.id
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

# Обработчик кнопки "👤 Профиль"
@dp.message(lambda m: m.text == "👤 Профиль")
async def profile(message: Message):
    cursor.execute(
        "SELECT username, phone FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )
    user = cursor.fetchone()

    cursor.execute(
        "SELECT COUNT(*) FROM food WHERE user_id = ?",
        (message.from_user.id,)
    )
    food_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM items WHERE user_id = ?",
        (message.from_user.id,)
    )
    items_count = cursor.fetchone()[0]

    username = f"@{user[0]}" if user and user[0] else "не указан"
    phone = user[1] if user and user[1] else "не привязан"

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Обновить контакт")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        f"👤 Твой профиль\n\n"
        f"🆔 ID: {message.from_user.id}\n"
        f"👤 Username: {username}\n"
        f"📱 Телефон: {phone}\n\n"
        f"🍔 Объявлений с едой: {food_count}\n"
        f"📦 Вещей в барахолке: {items_count}",
        reply_markup=keyboard
    )

# Обработчик кнопки "Обновить контакт"
@dp.message(lambda m: m.text in ["📱 Обновить контакт", "📱 Привязать / обновить контакт"])
async def update_contact(message: Message):
    await message.answer(
        "📱 Обнови контакт, чтобы с тобой могли связаться 👇",
        reply_markup=contact_keyboard
    )
@dp.message(lambda m: m.text == "🍔 Еда из общаг")
async def food_menu(message: Message):
    await message.answer(
        "🍔 Еда из общаг\n\n"
        "Пролистывай объявления и выбирай 👇",
        reply_markup=food_keyboard
    )

# ================== ITEMS SECTION ==================

# Меню раздела "Продажа различных вещей"
@dp.message(lambda m: m.text == "📦 Барахолка")
async def items_menu(message: Message):
    await message.answer(
        "📦 Барахолка\n\n"
        "Продажа и покупка любых вещей 👇",
        reply_markup=items_keyboard
    )


@dp.message(lambda m: m.text == "➕ Добавить вещь")
async def add_item(message: Message, state: FSMContext):
    if not await require_contact(message):
        return
    await message.answer("📸 Отправь фото вещи", reply_markup=cancel_keyboard)
    await state.set_state(AddItem.photo)


@dp.message(AddItem.photo)
async def item_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Нужно фото", reply_markup=cancel_keyboard)
        return
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("💰 Напиши цену", reply_markup=cancel_keyboard)
    await state.set_state(AddItem.price)


@dp.message(AddItem.price)
async def item_price(message: Message, state: FSMContext):
    await state.update_data(price=message.text)
    await message.answer("📝 Опиши вещь", reply_markup=cancel_keyboard)
    await state.set_state(AddItem.description)


@dp.message(AddItem.description)
async def item_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("🏠 Номер общежития (3 / 4 / 5)", reply_markup=cancel_keyboard)
    await state.set_state(AddItem.dorm)


@dp.message(AddItem.dorm)
async def item_dorm(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) not in [3, 4, 5]:
        await message.answer("❌ Введи 3, 4 или 5", reply_markup=cancel_keyboard)
        return
    await state.update_data(dorm=int(message.text))
    await message.answer("📍 Этаж и комната", reply_markup=cancel_keyboard)
    await state.set_state(AddItem.location)


@dp.message(AddItem.location)
async def item_finish(message: Message, state: FSMContext):
    data = await state.get_data()

    cursor.execute(
        "INSERT INTO items (user_id, photo, price, description, dorm, location, approved) VALUES (?, ?, ?, ?, ?, ?, 0)",
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
        "🆕 Новая вещь на модерации"
    )

    await state.clear()
    await message.answer(
        "⏳ Вещь отправлена на модерацию",
        reply_markup=main_keyboard
    )


@dp.message(lambda m: m.text == "⬅️ Назад")
async def back(message: Message):
    await message.answer("Главное меню", reply_markup=main_keyboard)




@dp.message(lambda m: m.text == "🛠 Услуги")
async def services(message: Message):
    await message.answer("🛠 Раздел скоро появится 👀")


# ================== ADD FOOD ==================
@dp.message(lambda m: m.text == "➕ Добавить еду")
async def add_food(message: Message, state: FSMContext):
    if not await require_contact(message):
        return
    await message.answer("📸 Отправь фото еды", reply_markup=cancel_keyboard)
    await state.set_state(AddFood.photo)



@dp.message(AddFood.photo)
async def add_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer(
            "❌ Нужно отправить именно ФОТО 📸\nПопробуй ещё раз",
            reply_markup=cancel_keyboard
        )
        return

    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer(
        "💰 Напиши цену (только цифры)",
        reply_markup=cancel_keyboard
    )
    await state.set_state(AddFood.price)


@dp.message(AddFood.price)
async def add_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer(
            "❌ Цена должна быть числом\nНапример: 150",
            reply_markup=cancel_keyboard
        )
        return

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
    if not message.text:
        await message.answer(
            "❌ Напиши этаж и комнату текстом\nНапример: 5 этаж, 213",
            reply_markup=cancel_keyboard
        )
        return

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

    await bot.send_message(
        ADMIN_ID,
        f"🆕 Новое объявление\n\n"
        f"👤 Пользователь: @{message.from_user.username or message.from_user.id}\n"
        f"🏠 Общага: {data['dorm']}\n"
        f"💰 Цена: {data['price']}"
    )

    await state.clear()

    await message.answer(
        "✅ Объявление успешно добавлено!\n\n"
        "Теперь его видят другие пользователи 👇",
        reply_markup=main_keyboard
    )


# ================== VIEW FOOD (SWIPE) ==================
@dp.message(lambda m: m.text == "📋 Смотреть еду")
async def view_food(message: Message):
    if not await require_contact(message):
        return
    cursor.execute(
        "SELECT id, user_id, photo, price, description, dorm, location, views FROM food ORDER BY id DESC"
    )
    foods = cursor.fetchall()

    if not foods:
        await message.answer("📭 Еды пока нет")
        return

    feed_index[message.from_user.id] = 0
    await show_food(message.from_user.id, message)


async def show_food(user_id: int, message: Message):
    cursor.execute(
        "SELECT id, user_id, photo, price, description, dorm, location, views FROM food ORDER BY id DESC"
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

    cursor.execute(
        "SELECT 1 FROM views WHERE user_id = ? AND food_id = ?",
        (user_id, food_id)
    )
    viewed = cursor.fetchone()

    if not viewed:
        cursor.execute(
            "INSERT INTO views (user_id, food_id) VALUES (?, ?)",
            (user_id, food_id)
        )
        cursor.execute(
            "UPDATE food SET views = views + 1 WHERE id = ?",
            (food_id,)
        )
        db.commit()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data="food_prev"),
                InlineKeyboardButton(text="❤️", callback_data=f"like:{food_id}"),
                InlineKeyboardButton(text="➡️", callback_data="food_next")
            ]
        ]
    )

    await message.answer_photo(
        photo=photo,
        caption=(
            f"🍔 Еда из общаг\n"
            f"📍 {current} / {total}\n\n"
            f"🏠 Общежитие: {dorm}\n"
            f"💰 Цена: {price} ₽\n"
            f"👀 Просмотров: {views+1}\n\n"
            f"{desc}\n\n"
            f"❤️ Нажми, чтобы связаться с продавцом"
        ),
        reply_markup=keyboard
    )


@dp.callback_query(lambda c: c.data == "food_next")
async def food_next(callback: CallbackQuery):
    user_id = callback.from_user.id
    feed_index[user_id] = feed_index.get(user_id, 0) + 1
    await callback.message.delete()
    await show_food(user_id, callback.message)

@dp.callback_query(lambda c: c.data == "food_prev")
async def food_prev(callback: CallbackQuery):
    user_id = callback.from_user.id
    feed_index[user_id] = max(0, feed_index.get(user_id, 0) - 1)
    await callback.message.delete()
    await show_food(user_id, callback.message)




@dp.callback_query(lambda c: c.data.startswith("like:"))
async def like_food(callback: CallbackQuery):
    food_id = int(callback.data.split(":")[1])
    buyer = callback.from_user

    cursor.execute(
        """
        SELECT food.user_id, food.dorm, food.location, users.username
        FROM food
        LEFT JOIN users ON food.user_id = users.user_id
        WHERE food.id = ?
        """,
        (food_id,)
    )
    row = cursor.fetchone()

    if not row:
        await callback.answer("❌ Объявление не найдено", show_alert=True)
        return

    seller_id, dorm, location, seller_username = row

    cursor.execute(
        "INSERT INTO likes (food_id, buyer_id, seller_id, created_at) VALUES (?, ?, ?, ?)",
        (food_id, buyer.id, seller_id, int(asyncio.get_event_loop().time()))
    )
    db.commit()

    buyer_text = (
        "📍 Где забрать еду\n\n"
        f"🏠 Общежитие: {dorm}\n"
        f"📍 Место: {location}\n\n"
    )

    if seller_username:
        buyer_text += f"👤 Продавец: https://t.me/{seller_username}"
    else:
        buyer_text += "👤 Продавец: username не указан"

    await callback.message.answer(buyer_text)

    # Формируем карточку покупателя (ВАРИАНТ А — сразу показываем)
    cursor.execute(
        "SELECT username, phone FROM users WHERE user_id = ?",
        (buyer.id,)
    )
    buyer_row = cursor.fetchone()

    buyer_text = "👤 Новый интерес к объявлению\n\n"

    if buyer_row:
        buyer_username, buyer_phone = buyer_row
        if buyer_username:
            buyer_text += f"🔗 Telegram: https://t.me/{buyer_username}\n"
        else:
            buyer_text += "❌ Telegram не указан\n"

        if buyer_phone:
            buyer_text += f"📱 Телефон: {buyer_phone}\n"
        else:
            buyer_text += "❌ Телефон не указан\n"
    else:
        buyer_text += "❌ Данные покупателя не найдены\n"

    try:
        await bot.send_message(
            seller_id,
            buyer_text
        )
    except:
        pass

    await callback.answer("❤️ Интерес отправлен")



# ================== MY ADS ==================
@dp.message(lambda m: m.text == "📢 Мои объявления")
async def my_ads(message: Message, state: FSMContext):
    await state.clear()

    cursor.execute(
        "SELECT COUNT(*) FROM food WHERE user_id = ?",
        (message.from_user.id,)
    )
    count = cursor.fetchone()[0]

    if count == 0:
        await message.answer(
            "📭 У тебя пока нет объявлений с едой",
            reply_markup=main_keyboard
        )
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍔 Моя еда")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )

    await message.answer("📢 Твои объявления", reply_markup=keyboard)


# ===== МОЯ ЕДА =====
@dp.message(lambda m: m.text == "🍔 Моя еда")
async def my_food(message: Message):
    cursor.execute(
        "SELECT id, photo, price, description, dorm, location "
        "FROM food WHERE user_id = ? ORDER BY id DESC",
        (message.from_user.id,)
    )
    foods = cursor.fetchall()

    if not foods:
        await message.answer(
            "📭 У тебя нет объявлений с едой",
            reply_markup=main_keyboard
        )
        return

    my_ads_index[message.from_user.id] = 0
    await show_my_food(message.from_user.id, message)


# ====== СВАЙПЫ ДЛЯ МОЕЙ ЕДЫ ======
async def show_my_food(user_id: int, message: Message):
    cursor.execute(
        "SELECT id, photo, price, description, dorm, location "
        "FROM food WHERE user_id = ? ORDER BY id DESC",
        (user_id,)
    )
    foods = cursor.fetchall()

    index = my_ads_index.get(user_id, 0)

    if index >= len(foods):
        index = 0
        my_ads_index[user_id] = 0

    food_id, photo, price, desc, dorm, loc = foods[index]
    total = len(foods)
    current = index + 1

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data="my_food_prev"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_food:{food_id}"),
                InlineKeyboardButton(text="➡️", callback_data="my_food_next")
            ]
        ]
    )

    await message.answer_photo(
        photo=photo,
        caption=(
            f"🍔 Моё объявление\n"
            f"📍 {current} / {total}\n\n"
            f"🏠 Общежитие: {dorm}\n"
            f"📍 {loc}\n"
            f"💰 {price}\n\n"
            f"{desc}"
        ),
        reply_markup=keyboard
    )


# ===== CALLBACK-ХЕНДЛЕРЫ СВАЙПОВ МОЯ ЕДА =====
@dp.callback_query(lambda c: c.data == "my_food_next")
async def my_food_next(callback: CallbackQuery):
    my_ads_index[callback.from_user.id] = my_ads_index.get(callback.from_user.id, 0) + 1
    await callback.message.delete()
    await show_my_food(callback.from_user.id, callback.message)


@dp.callback_query(lambda c: c.data == "my_food_prev")
async def my_food_prev(callback: CallbackQuery):
    my_ads_index[callback.from_user.id] = max(
        0, my_ads_index.get(callback.from_user.id, 0) - 1
    )
    await callback.message.delete()
    await show_my_food(callback.from_user.id, callback.message)


# ===== CALLBACK ДЛЯ УДАЛЕНИЯ ЕДЫ =====
@dp.callback_query(lambda c: c.data.startswith("delete_food:"))
async def delete_food(callback: CallbackQuery):
    food_id = int(callback.data.split(":")[1])

    cursor.execute(
        "DELETE FROM food WHERE id = ? AND user_id = ?",
        (food_id, callback.from_user.id)
    )
    db.commit()

    await callback.message.delete()
    await callback.answer("🗑 Объявление удалено")


# =========== МОИ ВЕЩИ (СВАЙПЫ) ===========
@dp.message(lambda m: m.text == "📦 Мои вещи")
async def my_items(message: Message):
    cursor.execute(
        "SELECT id, photo, price, description, dorm, location, approved "
        "FROM items WHERE user_id = ?",
        (message.from_user.id,)
    )
    items = cursor.fetchall()

    if not items:
        await message.answer("📭 У тебя нет вещей")
        return

    my_items_index[message.from_user.id] = 0
    await show_my_item(message.from_user.id, message)


async def show_my_item(user_id: int, message: Message):
    cursor.execute(
        "SELECT id, photo, price, description, dorm, location, approved "
        "FROM items WHERE user_id = ?",
        (user_id,)
    )
    items = cursor.fetchall()

    index = my_items_index.get(user_id, 0)
    if index >= len(items):
        index = 0
        my_items_index[user_id] = 0

    item_id, photo, price, desc, dorm, loc, approved = items[index]
    total = len(items)
    current = index + 1

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data="my_item_prev"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_item:{item_id}"),
                InlineKeyboardButton(text="➡️", callback_data="my_item_next")
            ]
        ]
    )

    await message.answer_photo(
        photo=photo,
        caption=(
            f"📦 Моя вещь\n"
            f"📍 {current} / {total}\n\n"
            f"🏠 Общага: {dorm}\n"
            f"📍 {loc}\n"
            f"💰 Цена: {price}\n"
            f"📌 Статус: {'🟢 Активно' if approved else '🟡 На модерации'}\n\n"
            f"{desc}"
        ),
        reply_markup=keyboard
    )


# =========== CALLBACK ДЛЯ МОИХ ВЕЩЕЙ ===========
@dp.callback_query(lambda c: c.data == "my_item_next")
async def my_item_next(callback: CallbackQuery):
    my_items_index[callback.from_user.id] += 1
    await callback.message.delete()
    await show_my_item(callback.from_user.id, callback.message)


@dp.callback_query(lambda c: c.data == "my_item_prev")
async def my_item_prev(callback: CallbackQuery):
    my_items_index[callback.from_user.id] = max(
        0, my_items_index.get(callback.from_user.id, 0) - 1
    )
    await callback.message.delete()
    await show_my_item(callback.from_user.id, callback.message)


@dp.callback_query(lambda c: c.data.startswith("delete_item:"))
async def delete_item(callback: CallbackQuery):
    item_id = int(callback.data.split(":")[1])

    cursor.execute(
        "DELETE FROM items WHERE id = ? AND user_id = ?",
        (item_id, callback.from_user.id)
    )
    db.commit()

    await callback.answer("🗑 Удалено")
    await callback.message.delete()
# ================== ADMIN ==================




# ================== ADMIN ==================
@dp.message(lambda m: m.text == "/admin")
async def admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа")
        return

    await message.answer("🔐 Админка", reply_markup=admin_keyboard)


# ================== ADMIN BROADCAST ==================
@dp.message(lambda m: m.text == "📣 Рассылка")
async def start_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        "📣 Введи текст рассылки\n\n"
        "❌ Отмена — чтобы выйти",
        reply_markup=cancel_keyboard
    )
    await state.set_state(Broadcast.text)


@dp.message(Broadcast.text)
async def send_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    text = message.text

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    sent = 0
    failed = 0

    for (user_id,) in users:
        try:
            await bot.send_message(user_id, text)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1

    await state.clear()

    await message.answer(
        f"✅ Рассылка завершена\n\n"
        f"📨 Отправлено: {sent}\n"
        f"⚠️ Ошибок: {failed}",
        reply_markup=admin_keyboard
    )


@dp.message(lambda m: m.text == "📊 Статистика")
async def admin_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT COUNT(*) FROM food")
    food_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM food")
    users = cursor.fetchone()[0]

    cursor.execute(
        "SELECT MIN(first_seen) FROM users"
    )
    first_seen = cursor.fetchone()[0]

    from datetime import datetime
    first_seen_text = (
        datetime.fromtimestamp(first_seen).strftime("%d.%m.%Y %H:%M")
        if first_seen else "нет данных"
    )

    await message.answer(
        f"📊 Статистика\n\n"
        f"🍔 Объявлений: {food_count}\n"
        f"👥 Пользователей: {users}\n"
        f"🕒 Первый вход: {first_seen_text}"
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



# ================== RUN ==================
# ================== RUN ==================
async def main():
    print("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

# ================== ITEMS SWIPE VIEW ==================
@dp.message(lambda m: m.text == "📋 Смотреть вещи")
async def view_items(message: Message):
    if not await require_contact(message):
        return
    cursor.execute(
        "SELECT id, user_id, photo, price, description, dorm, location, views "
        "FROM items WHERE approved = 1 ORDER BY id DESC"
    )
    items = cursor.fetchall()

    if not items:
        await message.answer("📭 Вещей пока нет")
        return

    items_feed_index[message.from_user.id] = 0
    await show_item(message.from_user.id, message)


async def show_item(user_id: int, message: Message):
    cursor.execute(
        "SELECT id, user_id, photo, price, description, dorm, location, views "
        "FROM items WHERE approved = 1 ORDER BY id DESC"
    )
    items = cursor.fetchall()

    index = items_feed_index.get(user_id, 0)

    if not items:
        await message.answer("📭 Вещей пока нет")
        return

    if index >= len(items):
        index = 0
        items_feed_index[user_id] = 0

    item_id, seller_id, photo, price, desc, dorm, loc, views = items[index]
    total = len(items)
    current = index + 1

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data="item_prev"),
                InlineKeyboardButton(text="❤️", callback_data=f"item_like:{item_id}"),
                InlineKeyboardButton(text="➡️", callback_data="item_next")
            ]
        ]
    )

    await message.answer_photo(
        photo=photo,
        caption=(
            f"📦 Барахолка\n"
            f"📍 {current} / {total}\n\n"
            f"🏠 Общежитие: {dorm}\n"
            f"💰 Цена: {price}\n\n"
            f"{desc}\n\n"
            f"❤️ Нажми, чтобы связаться с продавцом"
        ),
        reply_markup=keyboard
    )


@dp.callback_query(lambda c: c.data == "item_next")
async def item_next(callback: CallbackQuery):
    user_id = callback.from_user.id
    items_feed_index[user_id] = items_feed_index.get(user_id, 0) + 1
    await callback.message.delete()
    await show_item(user_id, callback.message)


@dp.callback_query(lambda c: c.data == "item_prev")
async def item_prev(callback: CallbackQuery):
    user_id = callback.from_user.id
    items_feed_index[user_id] = max(0, items_feed_index.get(user_id, 0) - 1)
    await callback.message.delete()
    await show_item(user_id, callback.message)


@dp.callback_query(lambda c: c.data.startswith("item_like:"))
async def item_like(callback: CallbackQuery):
    item_id = int(callback.data.split(":")[1])

    cursor.execute(
        "SELECT items.user_id, users.username "
        "FROM items LEFT JOIN users ON items.user_id = users.user_id "
        "WHERE items.id = ?",
        (item_id,)
    )
    row = cursor.fetchone()

    if not row:
        await callback.answer("❌ Не найдено", show_alert=True)
        return

    seller_id, username = row

    if username:
        text = f"👤 Продавец:\n👉 https://t.me/{username}"
    else:
        text = "❌ Продавец не указал username"

    try:
        await bot.send_message(
            seller_id,
            "❤️ Твоей вещью заинтересовались!\nЗайди в бота 👀"
        )
    except:
        pass

    await callback.answer()
    await callback.message.answer(text)
# =========== МОДЕРАЦИЯ ВЕЩЕЙ В АДМИНКЕ ===========
@dp.message(lambda m: m.text == "🛂 Модерация вещей")
async def admin_items_moderation(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    admin_items_index[message.from_user.id] = 0
    await show_items_moderation(message.from_user.id, message)


async def show_items_moderation(user_id: int, message: Message):
    cursor.execute(
        "SELECT id, photo, price, description, dorm, location "
        "FROM items WHERE approved = 0"
    )
    items = cursor.fetchall()

    if not items:
        await message.answer("✅ Нет вещей на модерации")
        return

    index = admin_items_index.get(user_id, 0)
    if index >= len(items):
        index = 0
        admin_items_index[user_id] = 0

    item_id, photo, price, desc, dorm, loc = items[index]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"item_reject:{item_id}"),
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"item_approve:{item_id}")
            ]
        ]
    )

    await message.answer_photo(
        photo=photo,
        caption=(
            f"📦 Вещь на модерации\n\n"
            f"🏠 Общага: {dorm}\n"
            f"📍 {loc}\n"
            f"💰 {price}\n\n"
            f"{desc}"
        ),
        reply_markup=keyboard
    )


# =========== CALLBACK ДЛЯ МОДЕРАЦИИ ВЕЩЕЙ ===========
@dp.callback_query(lambda c: c.data.startswith("item_approve:"))
async def approve_item(callback: CallbackQuery):
    item_id = int(callback.data.split(":")[1])

    cursor.execute(
        "UPDATE items SET approved = 1 WHERE id = ?",
        (item_id,)
    )
    db.commit()

    await callback.answer("✅ Одобрено")
    await callback.message.delete()


@dp.callback_query(lambda c: c.data.startswith("item_reject:"))
async def reject_item(callback: CallbackQuery):
    item_id = int(callback.data.split(":")[1])

    cursor.execute(
        "DELETE FROM items WHERE id = ?",
        (item_id,)
    )
    db.commit()



# Обработчик кнопки "📚 Учёба (скоро)"
@dp.message(lambda m: m.text == "📚 Учёба (скоро)")
async def study_soon(message: Message):
    await message.answer(
        "📚 Раздел «Учёба»\n\n"
        "Скоро здесь появятся конспекты,\n"
        "помощь с заданиями и услуги 👀",
        reply_markup=main_keyboard
    )