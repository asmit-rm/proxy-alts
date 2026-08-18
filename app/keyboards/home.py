from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📱 Available Products", callback_data="shop:countries"
                )
            ],
            [
                InlineKeyboardButton(text="💰 Deposit", callback_data="wallet:deposit"),
                InlineKeyboardButton(text="💳 Balance", callback_data="wallet:balance"),
            ],
            [
                InlineKeyboardButton(text="📦 My Orders", callback_data="orders:list"),
                InlineKeyboardButton(text="💬 Support", callback_data="support:open"),
            ],
        ]
    )
