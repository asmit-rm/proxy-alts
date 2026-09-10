from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func

from app.database.database import async_session_maker
from app.database.models import (
    Product,
    ProductStatus,
    StockNumber,
    StockStatus,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    User,
    UserStatus,
)
from app.keyboards.admin import (
    admin_panel_keyboard,
    cancel_keyboard,
    confirm_product_keyboard,
    inventory_list_keyboard,
    product_manage_keyboard,
)
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
    waiting_2fa = State()


class BroadcastStates(StatesGroup):
    waiting_message = State()
    confirm = State()


_login_clients = {}


# ==================== /admin ====================

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        await message.answer("⛔ Access denied. Owner only.")
        return

    await message.answer(
        "🛠 <b>ADMIN PANEL</b>\n\nSelect an option:",
        reply_markup=admin_panel_keyboard(),
        parse_mode="HTML",
    )


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
        parse_mode="HTML",
    )
    await callback.answer("Cancelled")


@router.callback_query(F.data == "admin:panel")
async def admin_panel_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>ADMIN PANEL</b>\n\nSelect an option:",
        reply_markup=admin_panel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ==================== ADD PRODUCT ====================

@router.callback_query(F.data == "admin:add_product")
async def start_add_product(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    await state.set_state(AddProductStates.country)
    await callback.message.edit_text(
        "🌍 <b>Send Country Name</b>\n\nExample: <code>India</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddProductStates.country)
async def process_country(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return

    await state.update_data(country=message.text.strip().title())
    await state.set_state(AddProductStates.quality)
    await message.answer(
        "💎 <b>Send Quality</b>\n\nOptions: <code>GOOD</code> or <code>PREMIUM</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(AddProductStates.quality)
async def process_quality(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return

    quality = message.text.strip().upper()
    if quality not in ("GOOD", "PREMIUM"):
        await message.answer("❌ Only <code>GOOD</code> or <code>PREMIUM</code>.", parse_mode="HTML")
        return

    await state.update_data(quality=quality)
    await state.set_state(AddProductStates.name)
    await message.answer(
        "📝 <b>Send Product Name</b>\n\nExample: <code>Premium Number</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(AddProductStates.name)
async def process_name(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return

    await state.update_data(name=message.text.strip())
    await state.set_state(AddProductStates.price)
    await message.answer(
        "💰 <b>Set Price</b>\n\nExample: <code>24</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
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

    data = await state.get_data()

    if data.get("action") == "change_price":
        product_id = data.get("product_id")
        async with async_session_maker() as session:
            result = await session.execute(select(Product).where(Product.id == product_id))
            product = result.scalar_one_or_none()
            if product:
                product.price = price
                await session.commit()
        await state.clear()
        await message.answer(
            f"✅ Price updated!\nProduct #{product_id}\nNew Price: <b>{format_money(price)}</b>",
            parse_mode="HTML",
        )
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
        parse_mode="HTML",
    )
    await callback.answer("✅ Product saved")


# ==================== NUMBER LOGIN + 2FA ====================

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
        await state.update_data(
            phone=phone,
            session_file=str(fulfillment._get_session_path(phone)),
        )
        await state.set_state(AddProductStates.waiting_2fa)
        await message.answer(
            f"✅ Already logged in: <code>{phone}</code>\n\n"
            f"🔐 <b>2FA password</b> bhejo.\n"
            f"Agar nahi hai to <code>skip</code> likho.",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
        return

    if result["status"] == "code_sent":
        _login_clients[phone] = result["client"]
        await state.update_data(phone=phone, phone_code_hash=result["phone_code_hash"])
        await state.set_state(AddProductStates.waiting_code)
        await message.answer(
            f"🔐 <b>Send the code</b>\n\nCode sent to <code>{phone}</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
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
        await message.answer("❌ Session expired. Start again.")
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
        # Telegram cloud password during login — ask user to type it for Telethon sign-in later if needed
        await message.answer(
            "⚠️ Is number pe Telegram 2FA ON hai.\n"
            "Abhi inventory 2FA alag save hoga.\n"
            "Pehle session complete karo / number pe 2FA off karke dubara try karo agar login fail ho.",
        )
        await state.clear()
        return

    if result["status"] != "success":
        await message.answer(f"❌ Login failed: {result.get('message', 'Unknown')}")
        await state.clear()
        return

    # SUCCESS → sirf 2FA poocho, stock abhi mat banao
    await state.update_data(
        phone=phone,
        session_file=result.get("session_file"),
        product_id=product_id,
    )
    await state.set_state(AddProductStates.waiting_2fa)
    await message.answer(
        f"✅ Login successful: <code>{phone}</code>\n\n"
        f"🔐 Ab <b>2FA password</b> bhejo (buyer ko milega).\n"
        f"Agar 2FA nahi hai to <code>skip</code> likho.",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )


@router.message(AddProductStates.waiting_2fa)
async def process_2fa(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return

    data = await state.get_data()
    phone = data.get("phone")
    product_id = data.get("product_id")
    session_file = data.get("session_file")

    if not phone or not product_id:
        await message.answer("❌ Data missing. Start again.")
        await state.clear()
        return

    twofa = message.text.strip()
    if twofa.lower() == "skip":
        twofa = None

    async with async_session_maker() as session:
        stock = StockNumber(
            product_id=product_id,
            phone=phone,
            status=StockStatus.AVAILABLE,
            session_file=session_file,
            twofa_password=twofa,
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

    twofa_text = f"<code>{twofa}</code>" if twofa else "None"
    await message.answer(
        f"✅ <b>Number saved in stock</b>\n\n"
        f"📱 <code>{phone}</code>\n"
        f"🔐 2FA: {twofa_text}\n"
        f"📦 Product #{product_id}\n"
        f"Ready for selling!",
        parse_mode="HTML",
    )
    logger.info("Stock saved phone=%s product_id=%s twofa=%s", phone, product_id, bool(twofa))


# ==================== INVENTORY ====================

@router.callback_query(F.data == "admin:inventory")
async def show_inventory(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    async with async_session_maker() as session:
        result = await session.execute(
            select(Product).where(Product.stock > 0).order_by(Product.id.desc())
        )
        products = list(result.scalars().all())

    if not products:
        await callback.message.edit_text(
            "📦 <b>Inventory</b>\n\nNo available stock right now.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin:panel")]]
            ),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            "📦 <b>Manage Inventory</b>\n\nOnly products with stock:",
            reply_markup=inventory_list_keyboard(products),
            parse_mode="HTML",
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
        await callback.answer("Not found", show_alert=True)
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
    await callback.message.edit_text(
        text,
        reply_markup=product_manage_keyboard(product.id),
        parse_mode="HTML",
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
        f"📱 <b>Send Number for login</b>\n\nProduct ID: #{product_id}\nExample: <code>+916628652867</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
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
        f"💰 <b>Send new price</b>\n\nProduct #{product_id}\nExample: <code>50</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
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
            msg = "🔴 Disabled"
        else:
            product.status = ProductStatus.ACTIVE
            msg = "🟢 Enabled"
        await session.commit()

    await callback.answer(msg, show_alert=True)
    callback.data = f"admin:product:{product_id}"
    await manage_product(callback)


# ==================== STATS / BROADCAST / USERS / PAYMENTS ====================

@router.callback_query(F.data == "admin:stats")
async def show_stats(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    async with async_session_maker() as session:
        total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
        total_products = (await session.execute(select(func.count(Product.id)))).scalar() or 0
        total_stock = (
            await session.execute(
                select(func.count(StockNumber.id)).where(StockNumber.status == StockStatus.AVAILABLE)
            )
        ).scalar() or 0
        total_orders = (await session.execute(select(func.count(Order.id)))).scalar() or 0
        completed_orders = (
            await session.execute(
                select(func.count(Order.id)).where(Order.status == OrderStatus.COMPLETED)
            )
        ).scalar() or 0
        pending_payments = (
            await session.execute(
                select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PENDING)
            )
        ).scalar() or 0
        revenue = (
            await session.execute(
                select(func.coalesce(func.sum(Order.amount), 0)).where(
                    Order.status == OrderStatus.COMPLETED
                )
            )
        ).scalar() or 0

    text = (
        f"📊 <b>STATISTICS</b>\n\n"
        f"👥 Users: <b>{total_users}</b>\n"
        f"📦 Products: <b>{total_products}</b>\n"
        f"📱 Stock: <b>{total_stock}</b>\n"
        f"🛒 Orders: <b>{total_orders}</b>\n"
        f"✅ Completed: <b>{completed_orders}</b>\n"
        f"💰 Revenue: <b>{format_money(revenue)}</b>\n"
        f"⏳ Pending payments: <b>{pending_payments}</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin:panel")]]
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return
    await state.set_state(BroadcastStates.waiting_message)
    await callback.message.edit_text(
        "📢 <b>Broadcast</b>\n\nSend message to broadcast:",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(BroadcastStates.waiting_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    await state.update_data(broadcast_text=message.text or message.caption)
    await state.set_state(BroadcastStates.confirm)
    await message.answer(
        f"📢 <b>Preview:</b>\n\n{message.text or message.caption}\n\nSend to all users?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🚀 SEND", callback_data="admin:broadcast_send"),
                    InlineKeyboardButton(text="❌ CANCEL", callback_data="admin:cancel"),
                ]
            ]
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:broadcast_send")
async def send_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    data = await state.get_data()
    text = data.get("broadcast_text")
    await state.clear()
    if not text:
        await callback.answer("No message", show_alert=True)
        return

    await callback.message.edit_text("⏳ Broadcasting...")
    async with async_session_maker() as session:
        result = await session.execute(select(User.telegram_id))
        user_ids = [row[0] for row in result.all()]

    success = failed = 0
    for uid in user_ids:
        try:
            await callback.bot.send_message(uid, text, parse_mode="HTML")
            success += 1
        except Exception:
            failed += 1

    await callback.message.edit_text(
        f"✅ Broadcast done\n🚀 {success} | ❌ {failed}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin:panel")]]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:users")
async def show_users(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    async with async_session_maker() as session:
        result = await session.execute(select(User).order_by(User.created_at.desc()).limit(20))
        users = list(result.scalars().all())

    if not users:
        text = "👥 No users yet."
    else:
        lines = ["👥 <b>Recent Users</b>\n"]
        for u in users:
            un = f"@{u.username}" if u.username else "—"
            lines.append(f"<code>{u.telegram_id}</code> | {un}\nBal: {format_money(u.balance)}")
        text = "\n\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin:panel")]]
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:payments")
async def show_pending_payments(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    async with async_session_maker() as session:
        result = await session.execute(
            select(Payment)
            .where(Payment.status == PaymentStatus.PENDING)
            .order_by(Payment.created_at.desc())
        )
        payments = list(result.scalars().all())

    if not payments:
        text = "💰 No pending payments."
    else:
        lines = ["💰 <b>Pending Payments</b>\n"]
        for p in payments:
            lines.append(f"#{p.id} | {format_money(p.amount)} | user_db:{p.user_id}")
        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin:panel")]]
        ),
        parse_mode="HTML",
    )
    await callback.answer()


# ==================== /delsession /addadmin /removeadmin ====================

@router.message(Command("delsession"))
async def cmd_delsession(message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        await message.answer("⛔ Owner only.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        await message.answer("Usage: /delsession +91xxxxxxxxxx")
        return

    phone = args[1].strip()
    if not phone.startswith("+"):
        await message.answer("❌ Number must start with +")
        return

    ok = await fulfillment.logout(phone)

    async with async_session_maker() as session:
        result = await session.execute(select(StockNumber).where(StockNumber.phone == phone))
        stock = result.scalar_one_or_none()
        if stock:
            stock.status = StockStatus.DISABLED
            stock.session_file = None
            await session.commit()

    if ok:
        await message.answer(f"✅ Session deleted\n📱 <code>{phone}</code>", parse_mode="HTML")
    else:
        await message.answer(
            f"⚠️ Logout attempted / file may already be gone\n📱 <code>{phone}</code>",
            parse_mode="HTML",
        )


@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        await message.answer("⛔ Only main owners.")
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Usage: /addadmin <telegram_id>")
        return

    try:
        tid = int(args[1])
    except ValueError:
        await message.answer("❌ Invalid ID")
        return

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == tid))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                telegram_id=tid,
                balance=Decimal("0.00"),
                status=UserStatus.ACTIVE,
                is_admin=True,
            )
            session.add(user)
        else:
            user.is_admin = True
        await session.commit()

    await message.answer(f"✅ Admin added: <code>{tid}</code>", parse_mode="HTML")


@router.message(Command("removeadmin"))
async def cmd_removeadmin(message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        await message.answer("⛔ Only main owners.")
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Usage: /removeadmin <telegram_id>")
        return

    try:
        tid = int(args[1])
    except ValueError:
        await message.answer("❌ Invalid ID")
        return

    if tid in settings.owner_ids:
        await message.answer("❌ Cannot remove OWNER_IDS.")
        return

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == tid))
        user = result.scalar_one_or_none()
        if not user or not user.is_admin:
            await message.answer("Not an admin.")
            return
        user.is_admin = False
        await session.commit()

    await message.answer(f"✅ Admin removed: <code>{tid}</code>", parse_mode="HTML")
