from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def wallet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 Deposit", callback_data="wallet:deposit"),
            ],
            [
                InlineKeyboardButton(text="📜 Transaction History", callback_data="wallet:history"),
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="home"),
            ],
        ]
    )


def deposit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="wallet:balance"),
            ],
        ]
    )


def insufficient_funds_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 Deposit", callback_data="wallet:deposit"),
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="home"),
            ],
        ]
    )
