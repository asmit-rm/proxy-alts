from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from config import settings

router = Router(name="support")


@router.callback_query(F.data == "support:open")
async def open_support(callback: CallbackQuery):
    text = (
        f"💬 <b>Support</b>\n\n"
        f"Need help? Contact us:\n"
        f"{settings.SUPPORT_USERNAME}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📩 Contact Support",
                    url=f"https://t.me/{settings.SUPPORT_USERNAME.lstrip('@')}"
                )
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="home")
            ],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest:
        try:
            await callback.message.edit_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    await callback.answer()
