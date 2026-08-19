from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def payment_review_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ APPROVE",
                    callback_data=f"payment:approve:{payment_id}"
                ),
                InlineKeyboardButton(
                    text="❌ REJECT",
                    callback_data=f"payment:reject:{payment_id}"
                ),
            ]
        ]
    )


def deposit_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ Cancel", callback_data="wallet:balance")
            ]
        ]
    )
