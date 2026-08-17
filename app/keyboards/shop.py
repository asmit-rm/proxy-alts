from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def countries_keyboard(countries: list[str]) -> InlineKeyboardMarkup:
    buttons = []

    for country in countries:
        # Simple emoji mapping (optional)
        emoji = {
            "India": "🇮🇳",
            "USA": "🇺🇸",
            "United Kingdom": "🇬🇧",
            "UAE": "🇦🇪",
            "Germany": "🇩🇪",
            "Canada": "🇨🇦",
            "Australia": "🇦🇺",
        }.get(country, "🌍")

        buttons.append([
            InlineKeyboardButton(
                text=f"{emoji} {country}",
                callback_data=f"shop:country:{country}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="🔙 Back", callback_data="home")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def qualities_keyboard(country: str, qualities: list[str]) -> InlineKeyboardMarkup:
    buttons = []

    for quality in qualities:
        emoji = "🟢" if quality.upper() == "GOOD" else "💎"
        buttons.append([
            InlineKeyboardButton(
                text=f"{emoji} {quality}",
                callback_data=f"shop:quality:{country}:{quality}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="🔙 Back", callback_data="shop:countries")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def product_keyboard(product_id: int, country: str, quality: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 Buy Now",
                    callback_data=f"shop:buy:{product_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Back",
                    callback_data=f"shop:quality:{country}:{quality}"
                )
            ],
        ]
    )


def no_stock_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="shop:countries")]
        ]
    )
