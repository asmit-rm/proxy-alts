from decimal import Decimal, InvalidOperation

from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from app.database.database import async_session_maker
from app.database.models import Product, ProductStatus, StockNumber, StockStatus
from app.keyboards.admin import admin_panel_keyboard, cancel_keyboard, confirm_product_keyboard
from app.services.fulfillment import FulfillmentProvider
from app.utils.validators import is_owner
from app.utils.helpers import format_money
from app.utils.logger import logger
from config import settings

router = Router(name="admin")
fulfillment = FulfillmentProvider()


class AddProductStates(StatesGroup):
    country = State()
    quality = State()
    name = State()
    price = State()
    waiting_number = State()
    waiting_code = State()


_login_clients = {}


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        await message.answer("⛔ Access denied. Owner only.")
        return

    text = "🛠 <b>ADMIN PANEL</b>\n\nSelect an option:"
    await message.answer(text, reply_markup=admin_panel_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin:cancel")
async def admin_cancel(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    phone = data.get("phone")
    if phone and phone in _login_clients:
        client = _login_clients.pop(phone, None)
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass

    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>ADMIN PANEL</b>\n\nSelect an option:",
        reply_markup=admin_panel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer("Cancelled")


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
        f"Confirm to save. After saving you will add numbers."
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
            stock=0,
            status=ProductStatus.ACTIVE,
            created_by=callback.from_user.id,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)

    await state.update_data(product_id=product.id)
    await state.set_state(AddProductStates.waiting_number)

    await callback.message.edit_text(
        f"✅ <b>Product Saved!</b> (ID: #{product.id})\n\n"
        f"📱 <b>Send Number for login</b>\n\n"
        f"Example: <code>+916628652867</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer("✅ Product saved")


@router.message(AddProductStates.waiting_number)
async def process_number(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return

    phone = message.text.strip()
    if not phone.startswith("+"):
        await message.answer("❌ Number must start with +\nExample: <code>+916628652867</code>", parse_mode="HTML")
        return

    await message.answer("⏳ Sending code request...")

    try:
        result = await fulfillment.start_login(phone)
    except Exception as e:
        logger.error("start_login error: %s", e)
        await message.answer(f"❌ Failed to send code: {e}")
        return

    if result["status"] == "already_logged_in":
        # Already has session → just add to stock
        data = await state.get_data()
        product_id = data.get("product_id")

        async with async_session_maker() as session:
            stock = StockNumber(
                product_id=product_id,
                phone=phone,
                status=StockStatus.AVAILABLE,
                session_file=str(fulfillment._get_session_path(phone)),
            )
            session.add(stock)

            result_db = await session.execute(select(Product).where(Product.id == product_id))
            product = result_db.scalar_one_or_none()
            if product:
                product.stock += 1
                if product.status == ProductStatus.SOLD_OUT:
                    product.status = ProductStatus.ACTIVE

            await session.commit()

        await message.answer(
            f"✅ Number already logged in & added to stock.\n"
            f"📱 <code>{phone}</code>\n"
            f"Stock increased by 1."
        )
        await state.clear()
        return

    if result["status"] == "code_sent":
        _login_clients[phone] = result["client"]
        await state.update_data(
            phone=phone,
            phone_code_hash=result["phone_code_hash"]
        )
        await state.set_state(AddProductStates.waiting_code)

        await message.answer(
            f"🔐 <b>Send the code</b>\n\n"
            f"Code sent to <code>{phone}</code>\n"
            f"Please enter the login code:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )


@router.message(AddProductStates.waiting_code)
async def process_code(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return

    code = message.text.strip()
    data = await state.get_data()
    phone = data.get("phone")
    phone_code_hash = data.get("phone_code_hash")
    product_id = data.get("product_id")

    client = _login_clients.get(phone)
    if not client:
        await message.answer("❌ Session expired. Please start again.")
        await state.clear()
        return

    await message.answer("⏳ Logging in...")

    result = await fulfillment.complete_login(
        client=client,
        phone=phone,
        code=code,
        phone_code_hash=phone_code_hash,
    )

    _login_clients.pop(phone, None)

    if result["status"] == "invalid_code":
        await message.answer("❌ Invalid code. Try again or cancel.")
        return

    if result["status"] == "2fa_required":
        await message.answer("❌ This number has 2FA enabled. Currently not supported.")
        await state.clear()
        return

    if result["status"] != "success":
        await message.answer(f"❌ Login failed: {result.get('message', 'Unknown error')}")
        await state.clear()
        return

    # Success → create StockNumber + increase stock
    async with async_session_maker() as session:
        stock = StockNumber(
            product_id=product_id,
            phone=phone,
            status=StockStatus.AVAILABLE,
            session_file=result.get("session_file"),
        )
        session.add(stock)

        result_db = await session.execute(select(Product).where(Product.id == product_id))
        product = result_db.scalar_one_or_none()
        if product:
            product.stock += 1
            if product.status == ProductStatus.SOLD_OUT:
                product.status = ProductStatus.ACTIVE

        await session.commit()

    await state.clear()

    await message.answer(
        f"✅ <b>Number/Session Saved</b>\n\n"
        f"📱 Number: <code>{phone}</code>\n"
        f"📦 Product ID: #{product_id}\n"
        f"Ready for selling!",
        parse_mode="HTML"
    )

    logger.info("Number logged in & stock updated: phone=%s product_id=%s", phone, product_id)

# ==================== MANAGE INVENTORY ====================

@router.callback_query(F.data == "admin:panel")
async def admin_panel_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>ADMIN PANEL</b>\n\nSelect an option:",
        reply_markup=admin_panel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin:inventory")
async def show_inventory(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    async with async_session_maker() as session:
        result = await session.execute(select(Product).order_by(Product.id.desc()))
        products = list(result.scalars().all())

    if not products:
        text = "📦 <b>Inventory</b>\n\nNo products yet."
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data="admin:panel")]
            ]),
            parse_mode="HTML"
        )
    else:
        text = "📦 <b>Manage Inventory</b>\n\nSelect a product:"
        from app.keyboards.admin import inventory_list_keyboard
        await callback.message.edit_text(
            text,
            reply_markup=inventory_list_keyboard(products),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:product:"))
async def manage_product(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    product_id = int(callback.data.split(":")[2])

    async with async_session_maker() as session:
        result = await session.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()

    if not product:
        await callback.answer("Product not found", show_alert=True)
        return

    text = (
        f"📦 <b>Product #{product.id}</b>\n\n"
        f"🌍 Country: <b>{product.country}</b>\n"
        f"💎 Quality: <b>{product.quality}</b>\n"
        f"📝 Name: <b>{product.name}</b>\n"
        f"💰 Price: <b>{format_money(product.price)}</b>\n"
        f"📦 Stock: <b>{product.stock}</b>\n"
        f"Status: <b>{product.status.value}</b>"
    )

    from app.keyboards.admin import product_manage_keyboard
    await callback.message.edit_text(
        text,
        reply_markup=product_manage_keyboard(product.id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:add_number:"))
async def start_add_number(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    product_id = int(callback.data.split(":")[2])
    await state.update_data(product_id=product_id)
    await state.set_state(AddProductStates.waiting_number)

    await callback.message.edit_text(
        f"📱 <b>Send Number for login</b>\n\n"
        f"Product ID: #{product_id}\n"
        f"Example: <code>+916628652867</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:change_price:"))
async def start_change_price(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    product_id = int(callback.data.split(":")[2])
    await state.update_data(product_id=product_id, action="change_price")
    await state.set_state(AddProductStates.price)

    await callback.message.edit_text(
        f"💰 <b>Send new price</b>\n\nProduct ID: #{product_id}\nExample: <code>50</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:toggle:"))
async def toggle_product(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    product_id = int(callback.data.split(":")[2])

    async with async_session_maker() as session:
        result = await session.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if not product:
            await callback.answer("Not found", show_alert=True)
            return

        if product.status == ProductStatus.ACTIVE:
            product.status = ProductStatus.DISABLED
            msg = "🔴 Product Disabled"
        else:
            product.status = ProductStatus.ACTIVE
            msg = "🟢 Product Enabled"

        await session.commit()

    await callback.answer(msg, show_alert=True)
    # Refresh view
    callback.data = f"admin:product:{product_id}"
    await manage_product(callback)
