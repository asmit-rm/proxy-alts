from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.database.database import async_session_maker
from app.database.models import OrderStatus
from app.keyboards.wallet import insufficient_funds_keyboard
from app.services.orders import OrderService
from app.services.products import ProductService
from app.services.users import UserService
from app.services.fulfillment import FulfillmentProvider
from app.utils.helpers import format_money
from app.utils.logger import logger

router = Router(name="orders")
fulfillment = FulfillmentProvider()


def delivery_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📩 Send Code",
                    callback_data=f"delivery:code:{order_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚪 Device Logout",
                    callback_data=f"delivery:logout:{order_id}"
                ),
                InlineKeyboardButton(
                    text="🔙 Back",
                    callback_data="orders:list"
                ),
            ],
        ]
    )


@router.callback_query(F.data == "orders:list")
async def show_orders(callback: CallbackQuery):
    async with async_session_maker() as session:
        service = OrderService(session)
        orders = await service.get_user_orders(callback.from_user.id)

    if not orders:
        text = "📦 <b>My Orders</b>\n\nYou have no orders yet."
    else:
        lines = ["📦 <b>My Orders</b>\n"]
        for order in orders:
            status_emoji = {
                OrderStatus.PENDING: "⏳",
                OrderStatus.PROCESSING: "🔄",
                OrderStatus.COMPLETED: "✅",
                OrderStatus.CANCELLED: "❌",
                OrderStatus.REFUNDED: "💸",
            }.get(order.status, "❓")

            lines.append(
                f"{status_emoji} <b>#{order.id}</b> | {order.country} - {order.quality}\n"
                f"💰 {format_money(order.amount)} | {order.status.value}\n"
                f"<i>{order.created_at.strftime('%d %b %Y %H:%M')}</i>"
            )
        text = "\n\n".join(lines)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="home")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("shop:buy:"))
async def buy_product(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[2])

    async with async_session_maker() as session:
        try:
            order_service = OrderService(session)
            order = await order_service.create_order_atomic(
                telegram_id=callback.from_user.id,
                product_id=product_id,
            )
        except ValueError as e:
            error_msg = str(e)

            if "Insufficient balance" in error_msg:
                user_service = UserService(session)
                user = await user_service.get_user(callback.from_user.id)
                balance = user.balance if user else 0

                product_service = ProductService(session)
                product = await product_service.get_product_by_id(product_id)
                price = product.price if product else 0

                text = (
                    f"❌ <b>INSUFFICIENT FUNDS</b>\n\n"
                    f"💳 Balance: <b>{format_money(balance)}</b>\n"
                    f"💰 Required: <b>{format_money(price)}</b>\n"
                    f"📉 Short: <b>{format_money(price - balance)}</b>"
                )
                await callback.message.edit_text(
                    text,
                    reply_markup=insufficient_funds_keyboard(),
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            await callback.answer(f"❌ {error_msg}", show_alert=True)
            return

        # Get product for fulfillment reference (number)
        product_service = ProductService(session)
        product = await product_service.get_product_by_id(product_id)
        number = product.fulfillment_reference if product else None

        user_service = UserService(session)
        user = await user_service.get_user(callback.from_user.id)

        # Update order with number + mark processing/completed
        if number:
            await order_service.update_order_status(
                order_id=order.id,
                status=OrderStatus.COMPLETED,
                fulfillment_data=number,
            )
            order.status = OrderStatus.COMPLETED
            order.fulfillment_data = number

    if number:
        text = (
            f"🎉 <b>Delivery Successful</b>\n\n"
            f"📱 Number: <code>{number}</code>\n\n"
            f"💰 Paid: <b>{format_money(order.amount)}</b>\n"
            f"💳 Remaining Balance: <b>{format_money(user.balance)}</b>\n"
            f"📦 Order ID: <code>#{order.id}</code>"
        )
        await callback.message.edit_text(
            text,
            reply_markup=delivery_keyboard(order.id),
            parse_mode="HTML"
        )
    else:
        text = (
            f"✅ <b>PURCHASE SUCCESSFUL</b>\n\n"
            f"💰 Paid: <b>{format_money(order.amount)}</b>\n"
            f"💳 Remaining Balance: <b>{format_money(user.balance)}</b>\n\n"
            f"📦 Order ID: <code>#{order.id}</code>\n"
            f"Status: Pending\n\n"
            f"Your number is being prepared..."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 My Orders", callback_data="orders:list")],
            [InlineKeyboardButton(text="🏠 Home", callback_data="home")],
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    await callback.answer("✅ Purchase successful!")
    logger.info("Order created: order_id=%s user=%s product=%s", order.id, callback.from_user.id, product_id)


@router.callback_query(F.data.startswith("delivery:code:"))
async def send_code(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[2])

    async with async_session_maker() as session:
        order_service = OrderService(session)
        order = await order_service.get_order(order_id)

        if not order or not order.fulfillment_data:
            await callback.answer("❌ Number not found for this order", show_alert=True)
            return

        # Security: only order owner can request code
        from app.database.models import User
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.id == order.user_id))
        user = result.scalar_one_or_none()
        if not user or user.telegram_id != callback.from_user.id:
            await callback.answer("⛔ Not your order", show_alert=True)
            return

        number = order.fulfillment_data

    await callback.answer("⏳ Getting code...")

    code = await fulfillment.get_code(number)

    if code:
        await callback.message.answer(
            f"🔐 <b>Your Code:</b> <code>{code}</code>",
            parse_mode="HTML"
        )
    else:
        await callback.message.answer(
            "❌ No code found right now.\nPlease try again after requesting OTP."
        )


@router.callback_query(F.data.startswith("delivery:logout:"))
async def device_logout(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[2])

    async with async_session_maker() as session:
        order_service = OrderService(session)
        order = await order_service.get_order(order_id)

        if not order or not order.fulfillment_data:
            await callback.answer("❌ Number not found", show_alert=True)
            return

        from app.database.models import User
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.id == order.user_id))
        user = result.scalar_one_or_none()
        if not user or user.telegram_id != callback.from_user.id:
            await callback.answer("⛔ Not your order", show_alert=True)
            return

        number = order.fulfillment_data

    success = await fulfillment.logout(number)

    if success:
        await callback.answer("✅ Device logged out", show_alert=True)
        await callback.message.answer(f"🚪 Session for <code>{number}</code> has been logged out.", parse_mode="HTML")
    else:
        await callback.answer("❌ Logout failed", show_alert=True)
