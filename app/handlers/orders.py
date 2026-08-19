from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.database.database import async_session_maker
from app.database.models import OrderStatus
from app.keyboards.home import home_keyboard
from app.keyboards.shop import product_keyboard
from app.keyboards.wallet import insufficient_funds_keyboard
from app.services.orders import OrderService
from app.services.products import ProductService
from app.services.users import UserService
from app.utils.helpers import format_money
from app.utils.logger import logger

router = Router(name="orders")


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

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
                # Get current balance
                user_service = UserService(session)
                user = await user_service.get_user(callback.from_user.id)
                balance = user.balance if user else 0

                product_service = Product
