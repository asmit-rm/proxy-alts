from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Add Product", callback_data="admin:add_product")
            ],
            [
                InlineKeyboardButton(text="📦 Manage Inventory", callback_data="admin:inventory")
            ],
            [
                InlineKeyboardButton(text="💰 Payments", callback_data="admin:payments"),
                InlineKeyboardButton(text="👥 Users", callback_data="admin:users"),
            ],
            [
                InlineKeyboardButton(text="📢 Broadcast", callback_data="admin:broadcast"),
                InlineKeyboardButton(text="📊 Statistics", callback_data="admin:stats"),
            ],
            [
                InlineKeyboardButton(text="🏠 Home", callback_data="home")
            ],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="admin:cancel")]
        ]
    )


def confirm_product_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ SAVE", callback_data="admin:save_product"),
                InlineKeyboardButton(text="❌ CANCEL", callback_data="admin:cancel"),
            ]
        ]
    )
