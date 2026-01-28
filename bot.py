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
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)


router = Router()

APP_VERSION = "step3-2026-01-28a"

# ============ CONFIG (env first) ============
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TECH_MODE = os.getenv("TECH_MODE", "false").strip().lower() in {"1", "true", "yes", "y"}

DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or os.getenv("DATABASE_PUBLIC_URL", "").strip()

logging.basicConfig(level=logging.INFO)
railway_env = os.getenv("RAILWAY_ENVIRONMENT", "")
logging.info("[boot] RAILWAY_ENVIRONMENT=%r", railway_env)
logging.info("[boot] APP_VERSION=%s", APP_VERSION)
logging.info("[boot] BOT_TOKEN present key=%s len=%d", "BOT_TOKEN" in os.environ, len(os.getenv("BOT_TOKEN", "")))
logging.info(
    "[boot] env keys (filtered)=%s",
    sorted(
        {
            k
            for k in os.environ.keys()
            if "TOKEN" in k or k in {"BOT_TOKEN", "ADMIN_ID", "TECH_MODE", "DATABASE_URL", "DATABASE_PUBLIC_URL"}
        }
    ),
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is empty. Set BOT_TOKEN environment variable.")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is empty. Add Postgres and connect it to this service so DATABASE_URL is available."
    )

# ============ DB (asyncpg) ============

_pool: Optional[asyncpg.Pool] = None


async def db_init() -> None:
    """Create pool and ensure tables exist."""
    global _pool

    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)

    async with _pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              user_id   BIGINT PRIMARY KEY,
              username  TEXT,
              phone     TEXT,
              is_verified BOOLEAN NOT NULL DEFAULT FALSE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ads (
              id        BIGSERIAL PRIMARY KEY,
              user_id   BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
              category  TEXT NOT NULL,
              photo_file_id TEXT,
              price     TEXT,
              description TEXT,
              approved  BOOLEAN NOT NULL DEFAULT FALSE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # Lightweight "migrations" for step 3
        await conn.execute("ALTER TABLE ads ADD COLUMN IF NOT EXISTS dorm INTEGER;")
        await conn.execute("ALTER TABLE ads ADD COLUMN IF NOT EXISTS location TEXT;")
        await conn.execute("ALTER TABLE ads ADD COLUMN IF NOT EXISTS views INTEGER NOT NULL DEFAULT 0;")

        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ads_category_created ON ads(category, created_at DESC);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ads_user_created ON ads(user_id, created_at DESC);")

    logging.info("[db] initialized pool and ensured tables")


def db_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool


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
            DO UPDATE SET username=EXCLUDED.username,
                          phone=EXCLUDED.phone,
                          is_verified=TRUE,
                          updated_at=NOW();
            """,
            user_id,
            username,
            phone,
        )


async def db_create_food_ad(
    user_id: int,
    photo_file_id: str,
    price: str,
    description: str,
    dorm: int,
    location: str,
) -> int:
    """Create a food ad. We set approved=TRUE because moderation is disabled."""
    async with db_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO ads(user_id, category, photo_file_id, price, description, dorm, location, approved)
            VALUES($1, 'food', $2, $3, $4, $5, $6, TRUE)
            RETURNING id;
            """,
            user_id,
            photo_file_id,
            price,
            description,
            dorm,
            location,
        )
        return int(row["id"])


async def db_list_food_ads(limit: int = 50) -> list[asyncpg.Record]:
    async with db_pool().acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM ads
            WHERE category='food' AND approved=TRUE
            ORDER BY created_at DESC
            LIMIT $1;
            """,
            limit,
        )


async def db_inc_views(ad_id: int) -> None:
    async with db_pool().acquire() as conn:
        await conn.execute("UPDATE ads SET views = views + 1 WHERE id=$1", ad_id)


async def db_get_ad(ad_id: int) -> Optional[asyncpg.Record]:
    async with db_pool().acquire() as conn:
        return await conn.fetchrow("SELECT * FROM ads WHERE id=$1", ad_id)


async def db_list_my_ads(user_id: int, limit: int = 50) -> list[asyncpg.Record]:
    async with db_pool().acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM ads
            WHERE user_id=$1
            ORDER BY created_at DESC
            LIMIT $2;
            """,
            user_id,
            limit,
        )


async def db_delete_ad(user_id: int, ad_id: int) -> bool:
    async with db_pool().acquire() as conn:
        res = await conn.execute("DELETE FROM ads WHERE id=$1 AND user_id=$2", ad_id, user_id)
        # res looks like 'DELETE 1'
        return res.endswith("1")


# ============ UI / KEYBOARDS ============

CANCEL_TEXT = "❌ Отмена"
BACK_TEXT = "⬅️ Назад"


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍔 Еда"), KeyboardButton(text="📚 Учёба")],
            [KeyboardButton(text="🛠 Услуги"), KeyboardButton(text="📢 Мои объявления")],
            [KeyboardButton(text="📱 Обновить контакт"), KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


def contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def food_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить еду"), KeyboardButton(text="📋 Смотреть еду")],
            [KeyboardButton(text=BACK_TEXT)],
        ],
        resize_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CANCEL_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def ad_feed_kb(ad_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data="food_prev"),
                InlineKeyboardButton(text="❤️ Забрать", callback_data=f"food_take:{ad_id}"),
                InlineKeyboardButton(text="➡️", callback_data="food_next"),
            ]
        ]
    )


def my_ads_kb(ad_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data="my_prev"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"my_del:{ad_id}"),
                InlineKeyboardButton(text="➡️", callback_data="my_next"),
            ]
        ]
    )


def _fmt_ad(ad: asyncpg.Record) -> str:
    price = ad.get("price") or "—"
    desc = (ad.get("description") or "").strip()
    dorm = ad.get("dorm")
    location = (ad.get("location") or "").strip()
    views = ad.get("views") or 0

    lines = [
        "🍔 *Еда*",
        f"💰 *Цена:* {price}",
        f"👁 *Просмотры:* {views}",
    ]
    if dorm is not None:
        lines.append(f"🏢 *Общага:* {dorm}")
    if location:
        lines.append(f"📍 *Место:* {location}")

    if desc:
        lines.append("\n📝 *Описание:*\n" + desc)

    lines.append(f"\n🆔 #{ad.get('id')}")
    return "\n".join(lines)


# ============ STATE (Food Add) ============

class FoodAdd(StatesGroup):
    photo = State()
    price = State()
    description = State()
    dorm = State()
    location = State()
    confirm = State()


# In-memory positions for browsing lists
_food_pos: dict[int, int] = {}
_my_pos: dict[int, int] = {}


async def ensure_verified(message: Message) -> bool:
    user = await db_get_user(message.from_user.id)
    return bool(user and user.get("is_verified"))


# ============ HANDLERS ============

@router.message(CommandStart())
async def start(message: Message):
    await db_upsert_user(message.from_user.id, message.from_user.username)

    user = await db_get_user(message.from_user.id)
    verified = bool(user and user.get("is_verified"))

    if not verified:
        await message.answer(
            "👋 *Привет!*\n\n"
            "Чтобы пользоваться ботом, нужно подтвердить номер.\n"
            "Нажми кнопку ниже и отправь свой контакт 👇",
            reply_markup=contact_kb(),
            parse_mode="Markdown",
        )
        return

    await message.answer(
        "✅ *Номер подтверждён!*\n\nВыбирай раздел в меню 👇",
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )


@router.message(Command("help"))
@router.message(F.text == "ℹ️ Помощь")
async def help_cmd(message: Message):
    await message.answer(
        "*Команды:*\n"
        "/start — меню\n"
        "/help — помощь\n\n"
        "*Правила:*\n"
        "— не спамь\n"
        "— указывай честное описание\n\n"
        "Если бот просит подтвердить номер — нажми ‘📱 Поделиться контактом’.",
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )


@router.message(F.contact)
async def on_contact(message: Message):
    if not message.contact or message.contact.user_id != message.from_user.id:
        await message.answer(
            "⚠️ Отправь *свой* контакт через кнопку ниже.",
            reply_markup=contact_kb(),
            parse_mode="Markdown",
        )
        return

    phone = (message.contact.phone_number or "").strip()
    if not phone:
        await message.answer("⚠️ Не удалось прочитать номер. Попробуй ещё раз.", reply_markup=contact_kb())
        return

    await db_set_phone_verified(message.from_user.id, message.from_user.username, phone)

    await message.answer(
        "✅ Спасибо! Номер подтверждён.\n\nТеперь ты можешь пользоваться ботом 👇",
        reply_markup=main_kb(),
    )


@router.message(F.text == "📱 Обновить контакт")
async def update_contact(message: Message):
    await message.answer(
        "Ок! Нажми кнопку и отправь контакт ещё раз 👇",
        reply_markup=contact_kb(),
    )


# --------- FOOD SECTION ---------

@router.message(F.text == "🍔 Еда")
async def food_enter(message: Message):
    if not await ensure_verified(message):
        await message.answer("Сначала подтвердите номер 👇", reply_markup=contact_kb())
        return
    await message.answer("🍔 *Раздел: Еда*", reply_markup=food_menu_kb(), parse_mode="Markdown")


@router.message(F.text == BACK_TEXT)
async def go_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню 👇", reply_markup=main_kb())


@router.message(F.text == CANCEL_TEXT)
async def cancel_any(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Ок, отменил ✅", reply_markup=main_kb())


@router.message(F.text == "➕ Добавить еду")
async def food_add_start(message: Message, state: FSMContext):
    if not await ensure_verified(message):
        await message.answer("Сначала подтвердите номер 👇", reply_markup=contact_kb())
        return

    await state.clear()
    await state.set_state(FoodAdd.photo)
    await message.answer(
        "📸 Пришли *фото* еды одним сообщением.",
        reply_markup=cancel_kb(),
        parse_mode="Markdown",
    )


@router.message(FoodAdd.photo, F.photo)
async def food_add_photo(message: Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=photo_file_id)

    await state.set_state(FoodAdd.price)
    await message.answer(
        "💰 Теперь напиши *цену* (например: `150` или `100-200`).",
        reply_markup=cancel_kb(),
        parse_mode="Markdown",
    )


@router.message(FoodAdd.photo)
async def food_add_photo_wrong(message: Message):
    await message.answer("Нужно именно *фото* 🙂", reply_markup=cancel_kb(), parse_mode="Markdown")


@router.message(FoodAdd.price)
async def food_add_price(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 64:
        await message.answer("Цена выглядит странно. Напиши короче 🙂", reply_markup=cancel_kb())
        return

    await state.update_data(price=text)
    await state.set_state(FoodAdd.description)
    await message.answer(
        "📝 Опиши, что это (состав/порция/когда готово).\n\n"
        "Можно 1–5 строк.",
        reply_markup=cancel_kb(),
    )


@router.message(FoodAdd.description)
async def food_add_description(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) < 3:
        await message.answer("Напиши чуть подробнее 🙂", reply_markup=cancel_kb())
        return

    await state.update_data(description=text)
    await state.set_state(FoodAdd.dorm)
    await message.answer(
        "🏢 Какая *общага*? (только цифра, например `3`) ",
        reply_markup=cancel_kb(),
        parse_mode="Markdown",
    )


@router.message(FoodAdd.dorm)
async def food_add_dorm(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    try:
        dorm = int(text)
    except ValueError:
        await message.answer("Нужно число 🙂 Например: 2", reply_markup=cancel_kb())
        return

    if dorm < 0 or dorm > 100:
        await message.answer("Слишком странное число 😅", reply_markup=cancel_kb())
        return

    await state.update_data(dorm=dorm)
    await state.set_state(FoodAdd.location)
    await message.answer(
        "📍 Где именно забрать? (пример: `у вахты`, `3 этаж, кухня`) ",
        reply_markup=cancel_kb(),
    )


@router.message(FoodAdd.location)
async def food_add_location(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) < 2:
        await message.answer("Укажи место чуть точнее 🙂", reply_markup=cancel_kb())
        return

    await state.update_data(location=text)

    data = await state.get_data()
    preview = (
        "✅ *Проверь объявление:*\n\n"
        f"💰 Цена: *{data.get('price')}*\n"
        f"🏢 Общага: *{data.get('dorm')}*\n"
        f"📍 Место: *{data.get('location')}*\n\n"
        f"📝 Описание:\n{data.get('description')}\n\n"
        "Отправить?\n"
        "— напиши `да` чтобы опубликовать\n"
        "— или `нет` чтобы отменить"
    )

    await state.set_state(FoodAdd.confirm)
    await message.answer_photo(
        photo=data["photo_file_id"],
        caption=preview,
        parse_mode="Markdown",
        reply_markup=cancel_kb(),
    )


@router.message(FoodAdd.confirm)
async def food_add_confirm(message: Message, state: FSMContext):
    text = (message.text or "").strip().lower()
    if text in {"да", "yes", "y"}:
        data = await state.get_data()
        ad_id = await db_create_food_ad(
            user_id=message.from_user.id,
            photo_file_id=data["photo_file_id"],
            price=data["price"],
            description=data["description"],
            dorm=int(data["dorm"]),
            location=data["location"],
        )
        await state.clear()
        await message.answer(
            f"🎉 Готово! Объявление опубликовано ✅\n\n🆔 #{ad_id}",
            reply_markup=food_menu_kb(),
        )
        return

    if text in {"нет", "no", "n"}:
        await state.clear()
        await message.answer("Ок, отменил ✅", reply_markup=food_menu_kb())
        return

    await message.answer("Напиши `да` или `нет` 🙂", reply_markup=cancel_kb())


@router.message(F.text == "📋 Смотреть еду")
async def food_feed_start(message: Message):
    if not await ensure_verified(message):
        await message.answer("Сначала подтвердите номер 👇", reply_markup=contact_kb())
        return

    ads = await db_list_food_ads(limit=100)
    if not ads:
        await message.answer("Пока нет объявлений 😅\nСтань первым — нажми ‘➕ Добавить еду’.", reply_markup=food_menu_kb())
        return

    _food_pos[message.from_user.id] = 0
    await send_food_at_pos(message, ads, 0)


async def send_food_at_pos(message: Message, ads: list[asyncpg.Record], pos: int):
    pos = max(0, min(pos, len(ads) - 1))
    ad = ads[pos]

    await db_inc_views(int(ad["id"]))
    # refresh views
    ad = await db_get_ad(int(ad["id"])) or ad

    caption = _fmt_ad(ad) + f"\n\n_{pos+1}/{len(ads)}_"
    await message.answer_photo(
        photo=ad.get("photo_file_id"),
        caption=caption,
        parse_mode="Markdown",
        reply_markup=ad_feed_kb(int(ad["id"]))
    )


@router.callback_query(F.data.in_({"food_prev", "food_next"}))
async def food_nav(call: CallbackQuery):
    user_id = call.from_user.id
    ads = await db_list_food_ads(limit=100)
    if not ads:
        await call.answer("Пусто")
        return

    cur = _food_pos.get(user_id, 0)
    if call.data == "food_next":
        cur = (cur + 1) % len(ads)
    else:
        cur = (cur - 1) % len(ads)

    _food_pos[user_id] = cur

    ad = ads[cur]
    await db_inc_views(int(ad["id"]))
    ad = await db_get_ad(int(ad["id"])) or ad

    caption = _fmt_ad(ad) + f"\n\n_{cur+1}/{len(ads)}_"

    # Edit message if possible
    try:
        await call.message.edit_media(
            media=call.message.photo[-1].as_(
                type="photo",
                media=ad.get("photo_file_id"),
                caption=caption,
                parse_mode="Markdown",
            ),
            reply_markup=ad_feed_kb(int(ad["id"])),
        )
    except Exception:
        # Fallback to sending a new message
        await call.message.answer_photo(
            photo=ad.get("photo_file_id"),
            caption=caption,
            parse_mode="Markdown",
            reply_markup=ad_feed_kb(int(ad["id"])),
        )

    await call.answer()


@router.callback_query(F.data.startswith("food_take:"))
async def food_take(call: CallbackQuery):
    try:
        ad_id = int(call.data.split(":", 1)[1])
    except Exception:
        await call.answer("Ошибка")
        return

    ad = await db_get_ad(ad_id)
    if not ad:
        await call.answer("Не найдено")
        return

    seller = await db_get_user(int(ad["user_id"]))
    phone = (seller.get("phone") if seller else None) or "(номер скрыт)"
    username = (seller.get("username") if seller else None)

    contact_line = f"📞 *Телефон:* `{phone}`"
    if username:
        contact_line += f"\n👤 *Telegram:* @{username}"

    dorm = ad.get("dorm")
    location = ad.get("location")

    text = (
        "❤️ *Забрать:*\n"
        f"🏢 Общага: *{dorm}*\n"
        f"📍 Место: *{location}*\n\n"
        f"{contact_line}"
    )

    await call.message.answer(text, parse_mode="Markdown")
    await call.answer("Отправил контакты")


# --------- MY ADS ---------

@router.message(F.text == "📢 Мои объявления")
async def my_ads_start(message: Message):
    if not await ensure_verified(message):
        await message.answer("Сначала подтвердите номер 👇", reply_markup=contact_kb())
        return

    ads = await db_list_my_ads(message.from_user.id, limit=100)
    if not ads:
        await message.answer("У тебя пока нет объявлений 😅", reply_markup=main_kb())
        return

    _my_pos[message.from_user.id] = 0
    await send_my_at_pos(message, ads, 0)


async def send_my_at_pos(message: Message, ads: list[asyncpg.Record], pos: int):
    pos = max(0, min(pos, len(ads) - 1))
    ad = ads[pos]

    caption = "📢 *Моё объявление*\n\n" + _fmt_ad(ad) + f"\n\n_{pos+1}/{len(ads)}_"
    if ad.get("photo_file_id"):
        await message.answer_photo(
            photo=ad.get("photo_file_id"),
            caption=caption,
            parse_mode="Markdown",
            reply_markup=my_ads_kb(int(ad["id"]))
        )
    else:
        await message.answer(caption, parse_mode="Markdown", reply_markup=my_ads_kb(int(ad["id"])))


@router.callback_query(F.data.in_({"my_prev", "my_next"}))
async def my_nav(call: CallbackQuery):
    user_id = call.from_user.id
    ads = await db_list_my_ads(user_id, limit=100)
    if not ads:
        await call.answer("Пусто")
        return

    cur = _my_pos.get(user_id, 0)
    if call.data == "my_next":
        cur = (cur + 1) % len(ads)
    else:
        cur = (cur - 1) % len(ads)

    _my_pos[user_id] = cur
    ad = ads[cur]

    caption = "📢 *Моё объявление*\n\n" + _fmt_ad(ad) + f"\n\n_{cur+1}/{len(ads)}_"

    try:
        if call.message.photo:
            await call.message.edit_caption(caption=caption, parse_mode="Markdown", reply_markup=my_ads_kb(int(ad["id"])))
        else:
            await call.message.edit_text(text=caption, parse_mode="Markdown", reply_markup=my_ads_kb(int(ad["id"])))
    except Exception:
        await call.message.answer(caption, parse_mode="Markdown", reply_markup=my_ads_kb(int(ad["id"])))

    await call.answer()


@router.callback_query(F.data.startswith("my_del:"))
async def my_delete(call: CallbackQuery):
    try:
        ad_id = int(call.data.split(":", 1)[1])
    except Exception:
        await call.answer("Ошибка")
        return

    ok = await db_delete_ad(call.from_user.id, ad_id)
    await call.answer("Удалено ✅" if ok else "Не удалось")

    # Refresh list
    ads = await db_list_my_ads(call.from_user.id, limit=100)
    if not ads:
        await call.message.answer("Теперь у тебя нет объявлений.")
        return

    cur = min(_my_pos.get(call.from_user.id, 0), len(ads) - 1)
    _my_pos[call.from_user.id] = cur

    # Send next snapshot
    await send_my_at_pos(call.message, ads, cur)


# --------- GLOBAL GUARD / STUBS ---------

@router.message()
async def global_guard(message: Message, state: FSMContext):
    # Skip contacts and /commands
    if message.contact:
        return
    if message.text and message.text.startswith("/"):
        return

    # During an FSM flow, ignore here
    if await state.get_state() is not None:
        return

    # Require verification
    if not await ensure_verified(message):
        await message.answer("Сначала подтвердите номер 👇", reply_markup=contact_kb())
        return

    if TECH_MODE:
        if ADMIN_ID and message.from_user.id == ADMIN_ID:
            return
        await message.answer(
            "🛠 Бот на технических работах.\n"
            "Скоро вернёмся — спасибо за терпение 🙏"
        )
        return

    # Simple stubs
    if message.text in {"📚 Учёба", "🛠 Услуги"}:
        await message.answer(
            "Этот раздел подключим следующим шагом 🙂\n"
            "Сейчас полностью работает *Еда* + *Мои объявления* ✅",
            reply_markup=main_kb(),
            parse_mode="Markdown",
        )
        return

    await message.answer("Не понял 😅 Нажми кнопку в меню или напиши /help", reply_markup=main_kb())


# ============ APP ENTRYPOINT ============

async def main() -> None:
    await db_init()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())