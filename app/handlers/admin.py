from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database.database import async_session_maker
from app.database.models import Product, ProductStatus
from app.keyboards.admin import admin_panel_keyboard, cancel_keyboard, confirm_product_keyboard
from app.utils.validators import is_owner
from app.utils.helpers import format_money
from app.utils.logger import logger
from config import settings

router = Router(name="admin")


class AddProductStates(StatesGroup):
    country = State()
    quality = State()
    name = State()
    price = State()
    # Number login states will be added later


# ==================== /admin ====================

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        await message.answer("⛔ Access denied. Owner only.")
        return

    text = "🛠 <b>ADMIN PANEL</b>\n\nSelect an option:"
    await message.answer(text, reply_markup=admin_panel_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin:cancel")
async def admin_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>ADMIN PANEL</b>\n\nSelect an option:",
        reply_markup=admin_panel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer("Cancelled")


# ==================== ADD PRODUCT FLOW ====================

@router.callback_query(F.data == "admin:add_product")
async def start_add_product(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    await state.set_state(AddProductStates.country)
    await callback.message.edit_text(
        "🌍 <b>Send Country Name</b>\n\nExample: <code>India</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AddProductStates.country)
async def process_country(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return

    country = message.text.strip().title()
    await state.update_data(country=country)
    await state.set_state(AddProductStates.quality)

    await message.answer(
        "💎 <b>Send Quality</b>\n\nOptions: <code>GOOD</code> or <code>PREMIUM</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AddProductStates.quality)
async def process_quality(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return

    quality = message.text.strip().upper()
    if quality not in ("GOOD", "PREMIUM"):
        await message.answer("❌ Only <code>GOOD</code> or <code>PREMIUM</code> allowed.", parse_mode="HTML")
        return

    await state.update_data(quality=quality)
    await state.set_state(AddProductStates.name)

    await message.answer(
        "📝 <b>Send Product Name</b>\n\nExample: <code>Premium Number</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AddProductStates.name)
async def process_name(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return

    name = message.text.strip()
    await state.update_data(name=name)
    await state.set_state(AddProductStates.price)

    await message.answer(
        "💰 <b>Set Price</b>\n\nExample: <code>24</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AddProductStates.price)
async def process_price(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return

    try:
        price = Decimal(message.text.strip())
        if price <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await message.answer("❌ Invalid price. Example: <code>24</code>", parse_mode="HTML")
        return

    await state.update_data(price=str(price))

    data = await state.get_data()

    text = (
        f"📦 <b>PRODUCT PREVIEW</b>\n\n"
        f"🌍 Country: <b>{data['country']}</b>\n"
        f"💎 Quality: <b>{data['quality']}</b>\n"
        f"📝 Name: <b>{data['name']}</b>\n"
        f"💰 Price: <b>{format_money(price)}</b>\n\n"
        f"Confirm to save. After saving you will add numbers one by one."
    )

    await message.answer(text, reply_markup=confirm_product_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin:save_product")
async def save_product(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    data = await state.get_data()

    if not data.get("country") or not data.get("price"):
        await callback.answer("❌ Data missing. Start again.", show_alert=True)
        await state.clear()
        return

    async with async_session_maker() as session:
        product = Product(
            country=data["country"],
            quality=data["quality"],
            name=data["name"],
            price=Decimal(data["price"]),
            stock=0,  # Numbers will be added one by one
            status=ProductStatus.ACTIVE,
            created_by=callback.from_user.id,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)

    await state.clear()

    await callback.message.edit_text(
        f"✅ <b>Product Saved!</b>\n\n"
        f"Product ID: <code>#{product.id}</code>\n"
        f"🌍 {product.country} | 💎 {product.quality}\n"
        f"💰 {format_money(product.price)}\n\n"
        f"Now you can add numbers to this product from Manage Inventory.\n"
        f"(Number login system coming next)",
        parse_mode="HTML"
    )
    await callback.answer("✅ Product saved")

    logger.info(
        "Product created: id=%s country=%s quality=%s price=%s by=%s",
        product.id, product.country, product.quality, product.price, callback.from_user.id
  )
