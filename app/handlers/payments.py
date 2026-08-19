from decimal import Decimal, InvalidOperation

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database.database import async_session_maker
from app.database.models import PaymentStatus
from app.keyboards.payment import payment_review_keyboard, deposit_cancel_keyboard
from app.keyboards.wallet import wallet_keyboard
from app.services.payments import PaymentService
from app.services.users import UserService
from app.utils.helpers import format_money
from app.utils.validators import is_owner
from app.utils.logger import logger
from config import settings

router = Router(name="payments")


class DepositStates(StatesGroup):
    waiting_screenshot = State()
    waiting_amount = State()


# ==================== USER DEPOSIT FLOW ====================

@router.callback_query(F.data == "wallet:deposit")
async def start_deposit(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DepositStates.waiting_screenshot)

    text = (
        f"💳 <b>DEPOSIT</b>\n\n"
        f"UPI ID:\n<code>{settings.UPI_ID}</code>\n\n"
        f"1️⃣ Payment bhejo is UPI pe\n"
        f"2️⃣ Payment ka <b>screenshot</b> bhejo"
    )

    await callback.message.edit_text(
        text,
        reply_markup=deposit_cancel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(DepositStates.waiting_screenshot, F.photo)
async def process_screenshot(message: Message, state: FSMContext):
    photo = message.photo[-1]
    await state.update_data(screenshot_file_id=photo.file_id)
    await state.set_state(DepositStates.waiting_amount)

    await message.answer(
        "💰 Ab <b>amount</b> bhejo\nExample: <code>500</code>",
        parse_mode="HTML",
        reply_markup=deposit_cancel_keyboard()
    )


@router.message(DepositStates.waiting_screenshot)
async def wrong_screenshot(message: Message):
    await message.answer("❌ Please send a <b>screenshot</b> (photo).", parse_mode="HTML")


@router.message(DepositStates.waiting_amount)
async def process_amount(message: Message, state: FSMContext, bot: Bot):
    try:
        amount = Decimal(message.text.strip())
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except (InvalidOperation, ValueError, AttributeError):
        await message.answer("❌ Invalid amount. Example: <code>500</code>", parse_mode="HTML")
        return

    data = await state.get_data()
    screenshot_file_id = data.get("screenshot_file_id")

    if not screenshot_file_id:
        await message.answer("❌ Screenshot missing. Please start again.")
        await state.clear()
        return

    async with async_session_maker() as session:
        user_service = UserService(session)
        db_user, _ = await user_service.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )

        payment_service = PaymentService(session)
        payment = await payment_service.create_payment(
            user_id=db_user.id,
            amount=amount,
            screenshot_file_id=screenshot_file_id,
        )

    await state.clear()

    await message.answer(
        f"✅ <b>Payment Submitted</b>\n\n"
        f"Payment ID: <code>#{payment.id}</code>\n"
        f"Amount: <b>{format_money(amount)}</b>\n\n"
        f"Please wait for owner approval.",
        parse_mode="HTML"
    )

    # Notify all owners
    username = f"@{message.from_user.username}" if message.from_user.username else "No username"
    caption = (
        f"💰 <b>NEW PAYMENT</b>\n\n"
        f"Payment ID: <code>#{payment.id}</code>\n\n"
        f"User: {username}\n"
        f"Telegram ID: <code>{message.from_user.id}</code>\n\n"
        f"Amount: <b>{format_money(amount)}</b>"
    )

    for owner_id in settings.owner_ids:
        try:
            await bot.send_photo(
                chat_id=owner_id,
                photo=screenshot_file_id,
                caption=caption,
                reply_markup=payment_review_keyboard(payment.id),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning("Could not notify owner %s: %s", owner_id, e)


# ==================== OWNER APPROVE / REJECT ====================

@router.callback_query(F.data.startswith("payment:approve:"))
async def approve_payment(callback: CallbackQuery, bot: Bot):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    payment_id = int(callback.data.split(":")[2])

    async with async_session_maker() as session:
        try:
            service = PaymentService(session)
            payment, user = await service.approve_payment(
                payment_id=payment_id,
                reviewer_id=callback.from_user.id,
            )
        except ValueError as e:
            await callback.answer(str(e), show_alert=True)
            return

    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n✅ <b>APPROVED</b> by {callback.from_user.id}",
        parse_mode="HTML"
    )
    await callback.answer("✅ Payment Approved")

    # Notify user
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=(
                f"✅ <b>PAYMENT APPROVED</b>\n\n"
                f"{format_money(payment.amount)} added to your wallet.\n\n"
                f"💳 Current Balance: <b>{format_money(user.balance)}</b>"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning("Could not notify user: %s", e)


@router.callback_query(F.data.startswith("payment:reject:"))
async def reject_payment(callback: CallbackQuery, bot: Bot):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Owner only", show_alert=True)
        return

    payment_id = int(callback.data.split(":")[2])

    async with async_session_maker() as session:
        try:
            service = PaymentService(session)
            payment = await service.reject_payment(
                payment_id=payment_id,
                reviewer_id=callback.from_user.id,
            )

            # Get user telegram_id
            from sqlalchemy import select
            from app.database.models import User
            result = await session.execute(select(User).where(User.id == payment.user_id))
            user = result.scalar_one_or_none()
        except ValueError as e:
            await callback.answer(str(e), show_alert=True)
            return

    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n❌ <b>REJECTED</b> by {callback.from_user.id}",
        parse_mode="HTML"
    )
    await callback.answer("❌ Payment Rejected")

    if user:
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    f"❌ <b>PAYMENT REJECTED</b>\n\n"
                    f"Please contact support.\n"
                    f"{settings.SUPPORT_USERNAME}"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning("Could not notify user: %s", e)
