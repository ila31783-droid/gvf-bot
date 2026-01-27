@router.message(lambda m: m.text == "👤 Профиль")
async def profile(message: Message):
    cursor.execute(
        "SELECT username, phone FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )
    row = cursor.fetchone()

    if not row:
        await message.answer(
            "👤 Профиль\n\n"
            "❌ Профиль не найден.\n"
            "Попробуй написать /start",
            reply_markup=main_keyboard
        )
        return

    username, phone = row

    username_text = f"@{username}" if username else "не указан"
    phone_text = phone if phone else "не указан"

    await message.answer(
        "👤 Профиль\n\n"
        f"👤 Username: {username_text}\n"
        f"📱 Телефон: {phone_text}",
        reply_markup=main_keyboard
    )