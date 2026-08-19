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


def inventory_list_keyboard(products: list) -> InlineKeyboardMarkup:
    buttons = []
    for p in products:
        status = "🟢" if p.status.value == "ACTIVE" else "🔴"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} #{p.id} | {p.country} {p.quality} | Stock: {p.stock} | ₹{p.price}",
                callback_data=f"admin:product:{p.id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="🔙 Back", callback_data="admin:panel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def product_manage_keyboard(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Add Number",
                    callback_data=f"admin:add_number:{product_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 Change Price",
                    callback_data=f"admin:change_price:{product_id}"
                ),
                InlineKeyboardButton(
                    text="🔴 Disable" if True else "🟢 Enable",
                    callback_data=f"admin:toggle:{product_id}"
                ),
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin:inventory")
            ],
        ]
    )
