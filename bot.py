MAINTENANCE_MODE = True
import asyncio
import os
import sqlite3
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, Text
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "ВСТАВЬ_ТОКЕН"
ADMIN_ID = 7204477763  # твой TG ID

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "db", "database.db")

db = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = db.cursor()

# Ensure tables exist
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        phone TEXT
    )
"""
)

# --- User helper ---
def get_user(user_id: int):
    cursor.execute(
        "SELECT user_id, username, phone FROM users WHERE user_id = ?",
        (user_id,)
    )
    return cursor.fetchone()
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS food_ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        photo_file_id TEXT,
        price TEXT,
        description TEXT,
        dorm TEXT,
        floor_room TEXT,
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    )
"""
)
db.commit()


class FoodStates(StatesGroup):
    photo = State()
    price = State()
    description = State()
    dorm = State()
    floor_room = State()


food_router = Dispatcher().include_router  # placeholder to avoid linter error
food_router = Dispatcher().router()  # will be replaced later


from aiogram import Router

maintenance_router = Router()

@maintenance_router.message()
async def maintenance_message(message: Message):
    await message.answer(
        "🛠 Технические работы\n\n"
        "Бот временно недоступен. Мы уже чиним — зайди чуть позже 🙏"
    )

@maintenance_router.callback_query()
async def maintenance_callback(callback: CallbackQuery):
    await callback.answer(
        "🛠 Технические работы. Попробуй позже 🙏",
        show_alert=True
    )

food_router = Router()

# User's feed index storage in memory, keyed by user_id
user_feed_index = {}


# Keyboard for dorm selection
dorm_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Общежитие 1", callback_data="dorm_1"),
            InlineKeyboardButton(text="Общежитие 2", callback_data="dorm_2"),
        ],
        [
            InlineKeyboardButton(text="Общежитие 3", callback_data="dorm_3"),
            InlineKeyboardButton(text="Общежитие 4", callback_data="dorm_4"),
        ],
    ]
)

# --- Main menu keyboard ---
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🍔 Еда из общаг")],
        [KeyboardButton(text="📢 Мои объявления")],
        [KeyboardButton(text="👤 Профиль")],
    ],
    resize_keyboard=True,
)

# Keyboard for like/dislike on ads
def get_swipe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️", callback_data="like"),
                InlineKeyboardButton(text="👎", callback_data="dislike"),
            ]
        ]
    )


# Keyboard for "Мои объявления"
def get_my_ads_keyboard(ad_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Удалить объявление", callback_data=f"delete_{ad_id}")]
        ]
    )

@dp.message(Command("start"))
async def start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username

    user = get_user(user_id)

    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        db.commit()

    user = get_user(user_id)

    if user[2]:  # phone already exists
        await message.answer(
            "👋 Добро пожаловать в ГВФ Маркет\n\n"
            "Это бета-версия, возможны ошибки.\n"
            "Выбирай раздел 👇",
            reply_markup=main_keyboard
        )
        return

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поделиться номером", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(
        "📱 Чтобы пользоваться ботом, нужно подтвердить номер.\n"
        "Номер сохраняется один раз и больше не запрашивается.",
        reply_markup=kb
    )

@dp.message(F.contact)
async def save_contact(message: Message):
    if not message.contact or message.contact.user_id != message.from_user.id:
        await message.answer("❌ Нужно отправить свой номер.")
        return

    phone = message.contact.phone_number

    cursor.execute(
        "UPDATE users SET phone = ? WHERE user_id = ?",
        (phone, message.from_user.id)
    )
    db.commit()

    await message.answer(
        "✅ Номер сохранён!\n\n"
        "Теперь ты можешь пользоваться ботом 👇",
        reply_markup=main_keyboard
    )


@food_router.message(F.text & ~F.command, state=FoodStates.price)
async def process_price(message: Message, state: FSMContext):
    price = message.text.strip()
    if not price:
        await message.answer("Цена не может быть пустой. Введите цену.")
        return
    await state.update_data(price=price)
    await message.answer("📝 Введите описание еды.")
    await state.set_state(FoodStates.description)


@food_router.message(F.text & ~F.command, state=FoodStates.description)
async def process_description(message: Message, state: FSMContext):
    description = message.text.strip()
    if not description:
        await message.answer("Описание не может быть пустым. Введите описание.")
        return
    await state.update_data(description=description)
    await message.answer("🏢 Выберите общежитие.", reply_markup=dorm_keyboard)
    await state.set_state(FoodStates.dorm)


@food_router.callback_query(F.data.startswith("dorm_"), state=FoodStates.dorm)
async def process_dorm(callback: CallbackQuery, state: FSMContext):
    dorm = callback.data.split("_", 1)[1]
    await state.update_data(dorm=dorm)
    await callback.message.answer("🏠 Введите этаж и комнату (например, 3/45).")
    await state.set_state(FoodStates.floor_room)
    await callback.answer()


@food_router.message(F.text & ~F.command, state=FoodStates.floor_room)
async def process_floor_room(message: Message, state: FSMContext):
    floor_room = message.text.strip()
    if not floor_room:
        await message.answer("Поле этаж/комната не может быть пустым. Введите этаж и комнату.")
        return
    data = await state.get_data()
    user_id = message.from_user.id

    cursor.execute(
        """
        INSERT INTO food_ads (user_id, photo_file_id, price, description, dorm, floor_room)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            data["photo_file_id"],
            data["price"],
            data["description"],
            data["dorm"],
            floor_room,
        ),
    )
    db.commit()

    await message.answer("✅ Объявление добавлено!")
    await state.clear()


@food_router.message(Text(text="🍔 Еда из общаг"))
async def show_food_feed(message: Message):
    user_id = message.from_user.id
    cursor.execute(
        "SELECT id FROM food_ads WHERE user_id != ? ORDER BY id DESC", (user_id,)
    )
    ads = cursor.fetchall()

    if not ads:
        await message.answer("Пока нет объявлений от других пользователей.")
        return

    user_feed_index[user_id] = 0
    await send_food_ad(message.chat.id, user_id)


async def send_food_ad(chat_id: int, user_id: int):
    index = user_feed_index.get(user_id, 0)
    cursor.execute(
        "SELECT id, photo_file_id, price, description FROM food_ads WHERE user_id != ? ORDER BY id DESC",
        (user_id,),
    )
    ads = cursor.fetchall()
    if not ads:
        return
    if index < 0 or index >= len(ads):
        # Reset index if out of bounds
        user_feed_index[user_id] = 0
        index = 0
    ad = ads[index]
    ad_id, photo_file_id, price, description = ad

    caption = f"💰 Цена: {price}\n📝 Описание: {description}"
    keyboard = get_swipe_keyboard()
    await Bot(BOT_TOKEN).send_photo(chat_id, photo_file_id, caption=caption, reply_markup=keyboard)


@food_router.callback_query(Text(text=["like", "dislike"]))
async def handle_swipe(callback: CallbackQuery):
    user_id = callback.from_user.id
    action = callback.data
    index = user_feed_index.get(user_id, 0)

    cursor.execute(
        "SELECT id, user_id, photo_file_id, price, description, dorm, floor_room FROM food_ads WHERE user_id != ? ORDER BY id DESC",
        (user_id,),
    )
    ads = cursor.fetchall()
    if not ads:
        await callback.answer("Объявлений нет.", show_alert=True)
        return

    if index < 0 or index >= len(ads):
        user_feed_index[user_id] = 0
        index = 0

    ad = ads[index]
    ad_id, ad_user_id, photo_file_id, price, description, dorm, floor_room = ad

    if action == "like":
        # Show location info after like
        location_text = f"🏢 Общежитие: {dorm}\n🏠 Этаж/Комната: {floor_room}"
        # notify seller about interest
        cursor.execute(
            "SELECT username FROM users WHERE user_id = ?",
            (ad_user_id,)
        )
        seller = cursor.fetchone()

        buyer_username = callback.from_user.username
        if seller and buyer_username:
            try:
                await Bot(BOT_TOKEN).send_message(
                    ad_user_id,
                    "❤️ Интерес к твоему объявлению!\n\n"
                    f"👤 Покупатель: @{buyer_username}\n"
                    "Можешь написать ему напрямую в Telegram."
                )
            except Exception:
                pass
        await callback.message.edit_caption(
            caption=(
                f"💰 Цена: {price}\n"
                f"📝 Описание: {description}\n\n"
                f"{location_text}"
            ),
            reply_markup=None,
        )
        await callback.answer("Вы поставили ❤️")
    else:
        # dislike: just move on
        await callback.answer("Вы поставили 👎")

    # Move to next ad
    user_feed_index[user_id] = index + 1
    if user_feed_index[user_id] >= len(ads):
        user_feed_index[user_id] = 0
        await callback.message.answer("Это было последнее объявление.")
    else:
        # Send next ad
        await send_food_ad(callback.message.chat.id, user_id)


@food_router.message(Text(text="📢 Мои объявления"))
async def my_food_ads(message: Message):
    user_id = message.from_user.id
    cursor.execute(
        "SELECT id, photo_file_id, price, description, dorm, floor_room FROM food_ads WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    )
    ads = cursor.fetchall()

    if not ads:
        await message.answer("У вас пока нет объявлений.")
        return

    for ad in ads:
        ad_id, photo_file_id, price, description, dorm, floor_room = ad
        caption = (
            f"💰 Цена: {price}\n"
            f"📝 Описание: {description}\n"
            f"🏢 Общежитие: {dorm}\n"
            f"🏠 Этаж/Комната: {floor_room}"
        )
        keyboard = get_my_ads_keyboard(ad_id)
        await message.answer_photo(photo_file_id, caption=caption, reply_markup=keyboard)


@food_router.callback_query(Text(startswith="delete_"))
async def delete_food_ad(callback: CallbackQuery):
    user_id = callback.from_user.id
    ad_id_str = callback.data.split("_", 1)[1]
    try:
        ad_id = int(ad_id_str)
    except ValueError:
        await callback.answer("Неверный идентификатор объявления.", show_alert=True)
        return

    cursor.execute("SELECT user_id FROM food_ads WHERE id = ?", (ad_id,))
    row = cursor.fetchone()
    if not row:
        await callback.answer("Объявление не найдено.", show_alert=True)
        return

    owner_id = row[0]
    if owner_id != user_id:
        await callback.answer("Вы можете удалять только свои объявления.", show_alert=True)
        return

    cursor.execute("DELETE FROM food_ads WHERE id = ?", (ad_id,))
    db.commit()
    await callback.answer("Объявление удалено.")
    await callback.message.delete()


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    if MAINTENANCE_MODE:
        dp.include_router(maintenance_router)
    else:
        dp.include_router(food_router)

    print("✅ BOT STARTED (Food module only)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
# --- Profile handler ---
@dp.message(Text(text="👤 Профиль"))
async def profile(message: Message):
    user = get_user(message.from_user.id)

    if not user or not user[2]:
        await message.answer("📱 Сначала нужно подтвердить номер через /start")
        return

    masked_phone = user[2][:-4] + "****"

    await message.answer(
        f"👤 Профиль\n\n"
        f"🆔 ID: {message.from_user.id}\n"
        f"📱 Телефон: {masked_phone}\n\n"
        f"Чтобы изменить номер — нажми /start"
    )