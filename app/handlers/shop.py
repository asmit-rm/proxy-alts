from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from app.database.database import async_session_maker
from app.keyboards.shop import (
    countries_keyboard,
    qualities_keyboard,
    product_keyboard,
    no_stock_keyboard,
)
from app.keyboards.home import home_keyboard
from app.services.products import ProductService
from app.utils.helpers import format_money
from app.utils.logger import logger

router = Router(name="shop")


@router.callback_query(F.data == "shop:countries")
async def show_countries(callback: CallbackQuery):
    async with async_session_maker() as session:
        service = ProductService(session)
        countries = await service.get_available_countries()

    if not countries:
        text = "❌ No products available right now."
        await callback.message.edit_text(text, reply_markup=no_stock_keyboard())
        await callback.answer()
        return

    text = "🌍 <b>Select Country</b>"
    await callback.message.edit_text(
        text,
        reply_markup=countries_keyboard(countries),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop:country:"))
async def show_qualities(callback: CallbackQuery):
    country = callback.data.split(":")[2]

    async with async_session_maker() as session:
        service = ProductService(session)
        qualities = await service.get_qualities_by_country(country)

    if not qualities:
        text = f"❌ No stock available for <b>{country}</b>."
        await callback.message.edit_text(text, reply_markup=no_stock_keyboard(), parse_mode="HTML")
        await callback.answer()
        return

    text = f"💎 <b>Select Quality</b>\n\n🌍 Country: <b>{country}</b>"
    await callback.message.edit_text(
        text,
        reply_markup=qualities_keyboard(country, qualities),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop:quality:"))
async def show_products(callback: CallbackQuery):
    parts = callback.data.split(":")
    country = parts[2]
    quality = parts[3]

    async with async_session_maker() as session:
        service = ProductService(session)
        products = await service.get_products(country, quality)

    if not products:
        text = f"❌ No products available for <b>{country}</b> - <b>{quality}</b>."
        await callback.message.edit_text(text, reply_markup=no_stock_keyboard(), parse_mode="HTML")
        await callback.answer()
        return

    # For now show first product (later we can show list if multiple)
    product = products[0]

    text = (
        f"📦 <b>Product Details</b>\n\n"
        f"🌍 Country: <b>{product.country}</b>\n"
        f"💎 Quality: <b>{product.quality}</b>\n"
        f"📝 {product.name}\n"
        f"💰 Price: <b>{format_money(product.price)}</b>\n"
        f"📦 Stock: <b>{product.stock}</b>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=product_keyboard(product.id, country, quality),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "home")
async def go_home(callback: CallbackQuery):
    from app.services.users import UserService
    from app.utils.helpers import format_money

    async with async_session_maker() as session:
        service = UserService(session)
        user = await service.get_user(callback.from_user.id)

    balance = format_money(user.balance) if user else "₹0.00"

    text = (
        f"👋 Welcome to <b>TG ALT STORE</b>!\n\n"
        f"💳 Balance: <b>{balance}</b>\n"
        f"🟢 Store Status: Online"
    )

    try:
        await callback.message.edit_text(text, reply_markup=home_keyboard(), parse_mode="HTML")
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=home_keyboard(), parse_mode="HTML")

    await callback.answer()
