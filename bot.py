import asyncio
import logging
import os
from typing import Optional

import asyncpg
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InputMediaPhoto,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# ================= APP =================

APP_VERSION = "step4-2026-01-28"

router = Router()
logging.basicConfig(level=logging.INFO)

# ================= ENV =================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or os.getenv("DATABASE_PUBLIC_URL", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is empty")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is empty")

logging.info("[boot] APP_VERSION=%s", APP_VERSION)
logging.info("[boot] ADMIN_ID=%s", ADMIN_ID)

# ================= DB =================

_pool: Optional[asyncpg.Pool] = None


async def db_init() -> None:
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)

    async with _pool.acquire() as conn:
        # users
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                phone TEXT,
                is_verified BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # ads
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ads (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                photo_file_id TEXT,
                price TEXT,
                description TEXT,
                dorm INTEGER,
                location TEXT,
                views INTEGER NOT NULL DEFAULT 0,
                approved BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # settings (tech mode)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )

        await conn.execute(
            """
            INSERT INTO settings(key, value)
            VALUES ('tech_mode', 'false')
            ON CONFLICT (key) DO NOTHING;
            """
        )

    logging.info("[db] initialized")


def db_pool() -> asyncpg.Pool:
    if not _pool:
        raise RuntimeError("DB not initialized")
    return _pool


# ================= DB HELPERS =================

async def db_get_user(user_id: int) -> Optional[asyncpg.Record]:
    async with db_pool().acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)


async def db_upsert_user(user_id: int, username: Optional[str]) -> None:
    async with db_pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users(user_id, username)
            VALUES($1, $2)
            ON CONFLICT (user_id)
            DO UPDATE SET username=EXCLUDED.username, updated_at=NOW();
            """,
            user_id,
            username,
        )


async def db_set_phone_verified(user_id: int, username: Optional[str], phone: str) -> None:
    async with db_pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users(user_id, username, phone, is_verified)
            VALUES($1, $2, $3, TRUE)
            ON CONFLICT (user_id)
            DO UPDATE SET
                username=EXCLUDED.username,
                phone=EXCLUDED.phone,
                is_verified=TRUE,
                updated_at=NOW();
            """,
            user_id,
            username,
            phone,
        )


async def db_is_tech_mode() -> bool:
    async with db_pool().acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key='tech_mode'")
        return row and row["value"] == "true"


async def db_set_tech_mode(value: bool) -> None:
    async with db_pool().acquire() as conn:
        await conn.execute(
            "UPDATE settings SET value=$1 WHERE key='tech_mode'",
            "true" if value else "false",
        )


# ================= HELPERS =================

def user_link_md(user_id: int, username: Optional[str], label: str) -> str:
    base = f"tg://user?id={user_id}"
    if username:
        return f"[{label} @{username}]({base})"
    return f"[{label}]({base})"


def chat_url(user_id: int, username: Optional[str]) -> str:
    return f"tg://user?id={user_id}" if user_id else (f"https://t.me/{username}" if username else "")

# ================= UI / KEYBOARDS =================

START_BTN_TEXT = "▶️ Начать"
HOME_TEXT = "🏠 Меню"


def start_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=START_BTN_TEXT, callback_data="start_go")]
        ]
    )


def main_menu_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🍔 Еда", callback_data="menu_food"),
                InlineKeyboardButton(text="📚 Учёба", callback_data="menu_study"),
            ],
            [
                InlineKeyboardButton(text="🛒 Барахолка", callback_data="menu_market"),
                InlineKeyboardButton(text="📢 Мои объявления", callback_data="menu_my"),
            ],
            [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu_help")],
        ]
    )


def back_menu_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=HOME_TEXT, callback_data="menu_home")]]
    )


def contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ================= FSM =================

class FoodAdd(StatesGroup):
    photo = State()
    price = State()
    description = State()
    dorm = State()
    location = State()
    confirm = State()


class AdminPanel(StatesGroup):
    delete_ad_id = State()
    broadcast_text = State()
    broadcast_confirm = State()


# ================= HELPERS =================

async def ensure_verified(message: Message) -> bool:
    user = await db_get_user(message.from_user.id)
    return bool(user and user["is_verified"])


# ================= START / ONBOARDING =================

@router.message(CommandStart())
async def cmd_start(message: Message):
    await db_upsert_user(message.from_user.id, message.from_user.username)

    user = await db_get_user(message.from_user.id)

    # If already verified — go straight to menu
    if user and user["is_verified"]:
        await message.answer(
            "🏠 *Главное меню*",
            reply_markup=main_menu_ikb(),
            parse_mode="Markdown",
        )
        return

    # Otherwise — show start button
    await message.answer(
        "👋 *Добро пожаловать в GVF Market*\n\n"
        "Здесь студенты продают и покупают еду и услуги в общаге.\n\n"
        "Нажми кнопку ниже, чтобы начать 👇",
        reply_markup=start_ikb(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "start_go")
async def start_go(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)

    # Если пользователь уже подтверждён — сразу показываем главное меню
    if user and user["is_verified"]:
        try:
            await call.message.edit_text(
                "🏠 *Главное меню*",
                reply_markup=main_menu_ikb(),
                parse_mode="Markdown",
            )
        except Exception:
            try:
                await call.message.delete()
            except Exception:
                pass
            await call.message.answer(
                "🏠 *Главное меню*",
                reply_markup=main_menu_ikb(),
                parse_mode="Markdown",
            )

        await call.answer()
        return

    # Иначе — просим подтвердить номер
    try:
        await call.message.delete()
    except Exception:
        pass

    await call.message.answer(
        "Для работы с ботом нужно подтвердить номер 📱",
        reply_markup=contact_kb(),
    )
    await call.answer()


@router.message(F.contact)
async def on_contact(message: Message):
    if not message.contact or message.contact.user_id != message.from_user.id:
        await message.answer("Отправь *свой* контакт 👇", reply_markup=contact_kb(), parse_mode="Markdown")
        return

    await db_set_phone_verified(
        message.from_user.id,
        message.from_user.username,
        message.contact.phone_number,
    )

    await message.answer(
        "✅ *Номер подтверждён!*\n\nВыбирай раздел 👇",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )

    await message.answer(
        "🏠 Главное меню",
        reply_markup=main_menu_ikb(),
    )


# ================= GLOBAL CANCEL =================

@router.message(Command("cancel"))
async def global_cancel(message: Message, state: FSMContext):
    if await state.get_state() is not None:
        await state.clear()

    await message.answer(
        "❌ Действие отменено\n\n🏠 Главное меню",
        reply_markup=main_menu_ikb(),
        parse_mode="Markdown",
    )


# ================= MAIN MENU =================

@router.callback_query(F.data == "menu_home")
async def menu_home(call: CallbackQuery):
    if await db_is_tech_mode() and call.from_user.id != ADMIN_ID:
        await call.answer("🛠 Техработы", show_alert=True)
        return

    try:
        # Works if message is text
        await call.message.edit_text(
            "🏠 *Главное меню*",
            reply_markup=main_menu_ikb(),
            parse_mode="Markdown",
        )
    except Exception:
        # Fallback for photo messages
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer(
            "🏠 *Главное меню*",
            reply_markup=main_menu_ikb(),
            parse_mode="Markdown",
        )

    await call.answer()


@router.callback_query(F.data == "menu_help")
async def menu_help(call: CallbackQuery):
    await call.message.edit_text(
        "ℹ️ *Помощь*\n\n"
        "• Добавляй честные объявления\n"
        "• Не спамь\n"
        "• Уважай других студентов",
        reply_markup=back_menu_ikb(),
        parse_mode="Markdown",
    )
    await call.answer()




# ================= MARKET (БАРАХОЛКА) =================

@router.callback_query(F.data == "menu_market")
async def menu_market(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    if not user or not user["is_verified"]:
        await call.answer("Подтверди номер через ▶️ Начать", show_alert=True)
        return
    if await db_is_tech_mode() and call.from_user.id != ADMIN_ID:
        await call.answer("🛠 Техработы", show_alert=True)
        return

    await call.message.edit_text(
        "🛒 *Барахолка*\n\n"
        "Здесь можно продавать и покупать вещи, технику и услуги.\n"
        "Скоро добавим объявления 👀",
        reply_markup=back_menu_ikb(),
        parse_mode="Markdown",
    )
    await call.answer()


# ================= ADS (FOOD) =================
_food_pos: dict[int, int] = {}
_my_pos: dict[int, int] = {}

@router.callback_query(F.data == "menu_my")
async def menu_my(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    if not user or not user["is_verified"]:
        await call.answer("Подтверди номер через ▶️ Начать", show_alert=True)
        return
    if await db_is_tech_mode() and call.from_user.id != ADMIN_ID:
        await call.answer("🛠 Техработы", show_alert=True)
        return

    async with db_pool().acquire() as conn:
        ads = await conn.fetch(
            "SELECT * FROM ads WHERE user_id=$1 ORDER BY created_at DESC LIMIT 50",
            call.from_user.id,
        )

    if not ads:
        await call.message.edit_text(
            "📭 *У тебя пока нет объявлений*",
            reply_markup=back_menu_ikb(),
            parse_mode="Markdown",
        )
        await call.answer()
        return

    _my_pos[call.from_user.id] = 0
    await show_my_ad(call, ads, 0)
    await call.answer()


async def db_create_food_ad(user_id: int, data: dict) -> int:
    async with db_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO ads(user_id, category, photo_file_id, price, description, dorm, location)
            VALUES($1, 'food', $2, $3, $4, $5, $6)
            RETURNING id
            """,
            user_id,
            data.get("photo"),
            data.get("price"),
            data.get("description"),
            data.get("dorm"),
            data.get("location"),
        )
        return int(row["id"])


async def db_list_food_ads() -> list[asyncpg.Record]:
    async with db_pool().acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM ads WHERE category='food' AND approved=TRUE ORDER BY created_at DESC LIMIT 50"
        )


async def db_delete_ad_admin(ad_id: int) -> bool:
    async with db_pool().acquire() as conn:
        res = await conn.execute("DELETE FROM ads WHERE id=$1", ad_id)
        return res.endswith("1")


async def db_list_verified_users() -> list[asyncpg.Record]:
    async with db_pool().acquire() as conn:
        return await conn.fetch("SELECT user_id FROM users WHERE is_verified=TRUE")


def food_view_ikb(ad_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data="food_prev"),
                InlineKeyboardButton(text="❤️ Забрать", callback_data=f"food_take:{ad_id}"),
                InlineKeyboardButton(text="➡️", callback_data="food_next"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_food")],
            [InlineKeyboardButton(text=HOME_TEXT, callback_data="menu_home")],
        ]
    )

@router.callback_query(F.data.in_({"food_prev", "food_next"}))
async def food_nav(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    if not user or not user["is_verified"]:
        await call.answer("Подтверди номер через ▶️ Начать", show_alert=True)
        return

    ads = await db_list_food_ads()
    if not ads:
        await call.answer("Пока нет объявлений", show_alert=True)
        return

    cur = _food_pos.get(call.from_user.id, 0)
    if call.data == "food_next":
        cur = (cur + 1) % len(ads)
    else:
        cur = (cur - 1) % len(ads)

    await show_food_at(call, ads, cur)
    await call.answer()
# === FOOD SECTION KEYBOARDS ===

def food_section_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Смотреть", callback_data="food_view"),
                InlineKeyboardButton(text="➕ Добавить", callback_data="food_add"),
            ],
            [InlineKeyboardButton(text=HOME_TEXT, callback_data="menu_home")],
        ]
    )


def food_cancel_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="food_cancel")]]
    )


def food_confirm_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Опубликовать", callback_data="food_publish")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="food_cancel")],
        ]
    )


def _fmt_food(ad: asyncpg.Record) -> str:
    return (
        "🍔 *Еда*\n\n"
        f"💰 Цена: *{ad['price']}*\n"
        f"🏢 Общага: *{ad['dorm']}*\n"
        "📍 Место: *после нажатия ❤️*\n\n"
        f"{ad['description'] or ''}\n"
        f"\n🆔 ID: `{ad['id']}`"
    )

def _food_caption(ad: asyncpg.Record, idx: int, total: int) -> str:
    return _fmt_food(ad) + f"\n\n_{idx+1}/{total}_"


async def show_food_at(call: CallbackQuery, ads: list[asyncpg.Record], idx: int) -> None:
    idx = max(0, min(idx, len(ads) - 1))
    _food_pos[call.from_user.id] = idx
    ad = ads[idx]

    caption = _food_caption(ad, idx, len(ads))
    ad_id = int(ad["id"])
    photo_id = ad.get("photo_file_id")

    # если текущее сообщение уже фото — пробуем edit_media
    try:
        if call.message.photo and photo_id:
            media = InputMediaPhoto(media=photo_id, caption=caption, parse_mode="Markdown")
            await call.message.edit_media(media=media, reply_markup=food_view_ikb(ad_id))
            return
    except Exception:
        pass

    # иначе удаляем старое и шлём новое фото
    try:
        await call.message.delete()
    except Exception:
        pass

    if photo_id:
        await call.message.answer_photo(
            photo=photo_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=food_view_ikb(ad_id),
        )
    else:
        await call.message.answer(
            caption,
            parse_mode="Markdown",
            reply_markup=food_view_ikb(ad_id),
        )

# ================= FOOD FLOW =================



# ==== FOOD SECTION MENU ====
@router.callback_query(F.data == "menu_food")
async def food_section(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    if not user or not user["is_verified"]:
        await call.answer("Подтверди номер через ▶️ Начать", show_alert=True)
        return
    if await db_is_tech_mode() and call.from_user.id != ADMIN_ID:
        await call.answer("🛠 Техработы", show_alert=True)
        return

    await call.message.edit_text(
        "🍔 *Раздел: Еда*\n\nВыбери действие:",
        reply_markup=food_section_ikb(),
        parse_mode="Markdown",
    )
    await call.answer()


# ==== FOOD VIEW LATEST ====
@router.callback_query(F.data == "food_view")
async def food_view(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    if not user or not user["is_verified"]:
        await call.answer("Подтверди номер через ▶️ Начать", show_alert=True)
        return
    if await db_is_tech_mode() and call.from_user.id != ADMIN_ID:
        await call.answer("🛠 Техработы", show_alert=True)
        return

    ads = await db_list_food_ads()
    if not ads:
        await call.message.edit_text(
            "😔 Пока нет объявлений.\n\nНажми ➕ Добавить и стань первым!",
            reply_markup=food_section_ikb(),
        )
        await call.answer()
        return

    await show_food_at(call, ads, 0)
    await call.answer()




# ==== FOOD ADD FLOW (FSM) ====
@router.callback_query(F.data == "food_add")
async def food_add_start(call: CallbackQuery, state: FSMContext):
    user = await db_get_user(call.from_user.id)
    if not user or not user["is_verified"]:
        await call.answer("Подтверди номер через ▶️ Начать", show_alert=True)
        return
    if await db_is_tech_mode() and call.from_user.id != ADMIN_ID:
        await call.answer("🛠 Техработы", show_alert=True)
        return

    await state.clear()
    await state.set_state(FoodAdd.photo)

    await call.message.answer(
        "📸 Пришли *фото* еды одним сообщением.",
        parse_mode="Markdown",
        reply_markup=food_cancel_ikb(),
    )
    await call.answer()


@router.callback_query(F.data == "food_cancel")
async def food_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text(
            "🍔 *Раздел: Еда*\n\nВыбери действие:",
            reply_markup=food_section_ikb(),
            parse_mode="Markdown",
        )
    except Exception:
        await call.message.answer("Ок, отменил ✅", reply_markup=food_section_ikb())
    await call.answer("Отменено")


@router.message(FoodAdd.photo, F.photo)
async def food_add_photo(message: Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await state.set_state(FoodAdd.price)
    await message.answer("💰 Напиши цену (пример: 150 или 100-200)", reply_markup=food_cancel_ikb())


@router.message(FoodAdd.photo)
async def food_add_photo_wrong(message: Message):
    await message.answer("Нужно отправить *фото* 🙂", parse_mode="Markdown", reply_markup=food_cancel_ikb())


@router.message(FoodAdd.price)
async def food_add_price(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 64:
        await message.answer("Цена выглядит странно. Напиши короче 🙂", reply_markup=food_cancel_ikb())
        return
    await state.update_data(price=text)
    await state.set_state(FoodAdd.description)
    await message.answer("📝 Опиши еду (1–5 строк)", reply_markup=food_cancel_ikb())


@router.message(FoodAdd.description)
async def food_add_desc(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 3:
        await message.answer("Напиши чуть подробнее 🙂", reply_markup=food_cancel_ikb())
        return
    await state.update_data(description=text)
    await state.set_state(FoodAdd.dorm)
    await message.answer("🏢 Какая общага? (цифра, например 3)", reply_markup=food_cancel_ikb())


@router.message(FoodAdd.dorm)
async def food_add_dorm(message: Message, state: FSMContext):
    try:
        dorm = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужно число 🙂", reply_markup=food_cancel_ikb())
        return
    if dorm < 0 or dorm > 100:
        await message.answer("Слишком странное число 😅", reply_markup=food_cancel_ikb())
        return
    await state.update_data(dorm=dorm)
    await state.set_state(FoodAdd.location)
    await message.answer("📍 Где можно забрать еду? (пример: на тумбе, в кубаре", reply_markup=food_cancel_ikb())


@router.message(FoodAdd.location)
async def food_add_location(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Укажи место чуть точнее 🙂", reply_markup=food_cancel_ikb())
        return

    await state.update_data(location=text)
    data = await state.get_data()

    preview = (
        "✅ *Проверь объявление:*\n\n"
        f"💰 Цена: *{data.get('price')}*\n"
        f"🏢 Общага: *{data.get('dorm')}*\n"
        f"📍 Место: *{data.get('location')}*\n\n"
        f"📝 Описание:\n{data.get('description')}\n"
    )

    await state.set_state(FoodAdd.confirm)
    await message.answer_photo(
        photo=data.get("photo"),
        caption=preview,
        parse_mode="Markdown",
        reply_markup=food_confirm_ikb(),
    )


@router.callback_query(F.data == "food_publish")
async def food_publish(call: CallbackQuery, state: FSMContext):
    user = await db_get_user(call.from_user.id)
    if not user or not user["is_verified"]:
        await call.answer("Подтверди номер через ▶️ Начать", show_alert=True)
        return

    data = await state.get_data()
    required = ["photo", "price", "description", "dorm", "location"]
    if not all(k in data and data[k] for k in required):
        await state.clear()
        await call.message.answer("⚠️ Данные не найдены, попробуй заново.", reply_markup=food_section_ikb())
        await call.answer()
        return

    ad_id = await db_create_food_ad(call.from_user.id, data)

    # Notify admin about new post
    if ADMIN_ID:
        try:
            await call.bot.send_message(
                ADMIN_ID,
                "🆕 Новое объявление (Еда) #{}\n".format(ad_id)
                + "От: {}\n".format(user_link_md(call.from_user.id, call.from_user.username, "продавец"))
                + "Цена: {}\n".format(data.get("price"))
                + "Общага: {}\n".format(data.get("dorm"))
                + "Место: {}\n\n".format(data.get("location"))
                + (data.get("description") or ""),
                parse_mode="Markdown",
            )
        except Exception:
            pass

    _food_pos[call.from_user.id] = 0
    await state.clear()

    await call.message.answer(
        f"🎉 Готово! Объявление опубликовано ✅\n🆔 ID: `{ad_id}`",
        parse_mode="Markdown",
        reply_markup=food_section_ikb(),
    )
    await call.answer("Опубликовано")



@router.callback_query(F.data.startswith("food_take:"))
async def food_take(call: CallbackQuery):
    user = await db_get_user(call.from_user.id)
    if not user or not user["is_verified"]:
        await call.answer("Подтверди номер через ▶️ Начать", show_alert=True)
        return

    ad_id = int(call.data.split(":")[1])
    async with db_pool().acquire() as conn:
        ad = await conn.fetchrow("SELECT * FROM ads WHERE id=$1", ad_id)

    if not ad:
        await call.answer("Не найдено", show_alert=True)
        return

    seller_id = int(ad["user_id"])
    seller = await db_get_user(seller_id)

    buyer = await db_get_user(call.from_user.id)

    seller_username = seller["username"] if seller else None
    buyer_username = call.from_user.username

    seller_phone = seller["phone"] if seller else "—"
    buyer_phone = buyer["phone"] if buyer else "—"

    # buyer -> seller
    kb_buyer = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать продавцу", url=chat_url(seller_id, seller_username))]
        ]
    )

    await call.message.answer(
        "❤️ *Контакты продавца*\n\n"
        f"📍 Где забрать: *{ad['location']}*\n"
        f"📞 `{seller_phone}`\n"
        f"👤 {('@' + seller_username) if seller_username else 'без username'}",
        reply_markup=kb_buyer,
        parse_mode="Markdown",
    )

    # seller notification
    kb_seller = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать покупателю", url=chat_url(call.from_user.id, buyer_username))]
        ]
    )

    await call.bot.send_message(
        seller_id,
        "❤️ *Твоё объявление заинтересовало покупателя!*\n\n"
        f"👤 {user_link_md(call.from_user.id, buyer_username, 'Покупатель')}\n"
        f"📞 `{buyer_phone}`\n\n"
        f"🆔 Объявление: `{ad_id}`",
        reply_markup=kb_seller,
        parse_mode="Markdown",
    )

    await call.answer("Контакты отправлены")

# ================= MY ADS =================

def my_ad_ikb(ad_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data="my_prev"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"my_del:{ad_id}"),
                InlineKeyboardButton(text="➡️", callback_data="my_next"),
            ],
            [InlineKeyboardButton(text=HOME_TEXT, callback_data="menu_home")],
        ]
    )


def _fmt_my_ad(ad: asyncpg.Record, idx: int, total: int) -> str:
    return (
        "📢 *Моё объявление*\n\n"
        f"💰 Цена: *{ad['price']}*\n"
        f"🏢 Общага: *{ad['dorm']}*\n"
        f"📍 Место: *{ad['location']}*\n\n"
        f"{ad['description'] or ''}\n\n"
        f"_ {idx+1}/{total} _\n"
        f"🆔 ID: `{ad['id']}`"
    )


async def show_my_ad(call: CallbackQuery, ads: list[asyncpg.Record], idx: int):
    idx = max(0, min(idx, len(ads) - 1))
    _my_pos[call.from_user.id] = idx
    ad = ads[idx]

    caption = _fmt_my_ad(ad, idx, len(ads))
    photo_id = ad.get("photo_file_id")
    ad_id = int(ad["id"])

    try:
        if call.message.photo and photo_id:
            media = InputMediaPhoto(
                media=photo_id,
                caption=caption,
                parse_mode="Markdown",
            )
            await call.message.edit_media(
                media=media,
                reply_markup=my_ad_ikb(ad_id),
            )
            return
    except Exception:
        pass

    try:
        await call.message.delete()
    except Exception:
        pass

    if photo_id:
        await call.message.answer_photo(
            photo=photo_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=my_ad_ikb(ad_id),
        )
    else:
        await call.message.answer(
            caption,
            parse_mode="Markdown",
            reply_markup=my_ad_ikb(ad_id),
        )


@router.callback_query(F.data.in_({"my_prev", "my_next"}))
async def my_ads_nav(call: CallbackQuery):
    async with db_pool().acquire() as conn:
        ads = await conn.fetch(
            "SELECT * FROM ads WHERE user_id=$1 ORDER BY created_at DESC LIMIT 50",
            call.from_user.id,
        )

    if not ads:
        await call.answer("Объявлений нет", show_alert=True)
        return

    cur = _my_pos.get(call.from_user.id, 0)
    cur = cur + 1 if call.data == "my_next" else cur - 1
    cur %= len(ads)

    await show_my_ad(call, ads, cur)
    await call.answer()


@router.callback_query(F.data.startswith("my_del:"))
async def my_ads_delete(call: CallbackQuery):
    ad_id = int(call.data.split(":")[1])

    async with db_pool().acquire() as conn:
        res = await conn.execute(
            "DELETE FROM ads WHERE id=$1 AND user_id=$2",
            ad_id,
            call.from_user.id,
        )

    if not res.endswith("1"):
        await call.answer("Не удалось удалить", show_alert=True)
        return

    async with db_pool().acquire() as conn:
        ads = await conn.fetch(
            "SELECT * FROM ads WHERE user_id=$1 ORDER BY created_at DESC LIMIT 50",
            call.from_user.id,
        )

    if not ads:
        await call.message.edit_text(
            "📭 Все объявления удалены",
            reply_markup=back_menu_ikb(),
        )
        await call.answer()
        return

    cur = min(_my_pos.get(call.from_user.id, 0), len(ads) - 1)
    await show_my_ad(call, ads, cur)
    await call.answer("Удалено ✅")

# ================= ADMIN =================

def admin_panel_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить объявление", callback_data="admin_del")],
            [InlineKeyboardButton(text="📣 Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🛠 Техработы", callback_data="admin_tech")],
            [InlineKeyboardButton(text=HOME_TEXT, callback_data="menu_home")],
        ]
    )


@router.message(Command("admin"))
async def admin_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔️ Нет доступа")
        return

    await message.answer(
        "🛡 *Админ-панель*",
        reply_markup=admin_panel_ikb(),
        parse_mode="Markdown",
    )



@router.callback_query(F.data == "admin_tech")
async def admin_tech(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    current = await db_is_tech_mode()
    new_state = not current
    await db_set_tech_mode(new_state)

    await call.message.edit_text(
        f"🛠 Техработы: *{'ВКЛ' if new_state else 'ВЫКЛ'}*",
        reply_markup=admin_panel_ikb(),
        parse_mode="Markdown",
    )
    await call.answer()


@router.callback_query(F.data == "admin_del")
async def admin_del(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return

    await state.set_state(AdminPanel.delete_ad_id)
    await call.message.answer("Введи ID объявления")


@router.message(AdminPanel.delete_ad_id)
async def admin_del_id(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        ad_id = int(message.text)
    except ValueError:
        await message.answer("Нужно число")
        return

    ok = await db_delete_ad_admin(ad_id)
    await state.clear()

    await message.answer("✅ Удалено" if ok else "❌ Не найдено", reply_markup=admin_panel_ikb())


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return

    await state.set_state(AdminPanel.broadcast_text)
    await call.message.answer("Пришли текст рассылки")


@router.message(AdminPanel.broadcast_text)
async def admin_broadcast_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(AdminPanel.broadcast_confirm)
    await message.answer(
        "Отправить рассылку?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да", callback_data="admin_send")],
                [InlineKeyboardButton(text="❌ Нет", callback_data="admin_cancel")],
            ]
        ),
    )



@router.callback_query(F.data == "admin_send")
async def admin_send(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("text"):
        await call.answer("Текст рассылки пуст", show_alert=True)
        return
    users = await db_list_verified_users()

    for u in users:
        try:
            await call.bot.send_message(u["user_id"], data["text"])
        except Exception:
            pass

    await state.clear()
    await call.message.answer("📣 Рассылка отправлена", reply_markup=admin_panel_ikb())


@router.callback_query(F.data == "admin_cancel")
async def admin_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("Отменено", reply_markup=admin_panel_ikb())



# ================= RUN =================

async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await db_init()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
