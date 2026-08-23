from decimal import Decimal, InvalidOperation

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sqlalchemy import select

from app.database.database import async_session_maker
from app.database.models import User
from app.keyboards.payment import (
    payment_review_keyboard,
    deposit_cancel_keyboard,
)
from app.services.payments import PaymentService
from app.services.users import UserService
from app.utils.helpers import format_money
from app.utils.validators import is_owner
from app.utils.logger import logger
from config import settings


router = Router(name="payments")


# ============================================================
# DEPOSIT STATES
# ============================================================

class DepositStates(StatesGroup):
    waiting_screenshot = State()
    waiting_amount = State()


# ============================================================
# START DEPOSIT
# ============================================================

QR_URL = "https://ucarecdn.com/667e6822-7a20-4368-a7e9-37cc0898d31f/"

@router.callback_query(F.data == "wallet:deposit")
async def start_deposit(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DepositStates.waiting_screenshot)

    text = (
        f"💳 <b>DEPOSIT</b>\n\n"
        f"UPI ID:\n<code>{settings.UPI_ID}</code>\n\n"
        f"1️⃣ Scan QR / pay on this UPI\n"
        f"2️⃣ Send payment <b>screenshot</b> here"
    )

    # Naya message with QR (photo start se conflict nahi hoga)
    await callback.message.answer_photo(
        photo=QR_URL,
        caption=text,
        reply_markup=deposit_cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()
# ============================================================
# RECEIVE SCREENSHOT
# ============================================================

@router.message(
    DepositStates.waiting_screenshot,
    F.photo,
)
async def process_screenshot(
    message: Message,
    state: FSMContext,
):
    if not message.photo:
        await message.answer(
            "❌ Please send a payment screenshot."
        )
        return

    # Highest quality photo
    photo = message.photo[-1]

    await state.update_data(
        screenshot_file_id=photo.file_id
    )

    await state.set_state(
        DepositStates.waiting_amount
    )

    await message.answer(
        "💰 <b>Payment amount bhejo</b>\n\n"
        "Example:\n"
        "<code>500</code>",
        parse_mode="HTML",
        reply_markup=deposit_cancel_keyboard(),
    )


# ============================================================
# WRONG SCREENSHOT INPUT
# ============================================================

@router.message(DepositStates.waiting_screenshot)
async def wrong_screenshot(message: Message):
    await message.answer(
        "❌ Please send the payment screenshot as a photo."
    )


# ============================================================
# PROCESS AMOUNT
# ============================================================

@router.message(DepositStates.waiting_amount)
async def process_amount(
    message: Message,
    state: FSMContext,
    bot: Bot,
):
    # --------------------------------------------------------
    # Validate amount
    # --------------------------------------------------------

    if not message.text:
        await message.answer(
            "❌ Please send amount.\n\n"
            "Example: <code>500</code>",
            parse_mode="HTML",
        )
        return

    try:
        amount = Decimal(
            message.text.strip()
        )

        if amount <= 0:
            raise ValueError

    except (InvalidOperation, ValueError):
        await message.answer(
            "❌ Invalid amount.\n\n"
            "Example: <code>500</code>",
            parse_mode="HTML",
        )
        return

    # --------------------------------------------------------
    # Get screenshot from FSM
    # --------------------------------------------------------

    data = await state.get_data()

    screenshot_file_id = data.get(
        "screenshot_file_id"
    )

    if not screenshot_file_id:
        await state.clear()

        await message.answer(
            "❌ Screenshot not found.\n\n"
            "Please start the deposit again."
        )
        return

    # --------------------------------------------------------
    # IMPORTANT:
    # Save CURRENT user's Telegram information
    # --------------------------------------------------------

    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    # --------------------------------------------------------
    # Create payment
    # --------------------------------------------------------

    try:
        async with async_session_maker() as session:

            user_service = UserService(session)

            db_user, _ = await user_service.get_or_create_user(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )

            payment_service = PaymentService(session)

            payment = await payment_service.create_payment(
                user_id=db_user.id,
                amount=amount,
                screenshot_file_id=screenshot_file_id,
            )

    except Exception:
        logger.exception(
            "Failed to create payment for user %s",
            telegram_id,
        )

        await message.answer(
            "❌ Payment submit nahi ho saka.\n\n"
            "Please try again later."
        )
        return

    # --------------------------------------------------------
    # Clear user state
    # --------------------------------------------------------

    await state.clear()

    # --------------------------------------------------------
    # Tell USER that payment was submitted
    # --------------------------------------------------------

    await message.answer(
        "✅ <b>PAYMENT SUBMITTED</b>\n\n"
        f"🧾 Payment ID: <code>#{payment.id}</code>\n"
        f"💰 Amount: <b>{format_money(amount)}</b>\n\n"
        "📸 Screenshot owner ko approval ke liye bhej diya gaya hai.\n"
        "⏳ Please wait for approval.",
        parse_mode="HTML",
    )

    # ========================================================
    # OWNER NOTIFICATION
    # ========================================================

    display_username = (
        f"@{username}"
        if username
        else "No username"
    )

    display_name = (
        first_name or "Unknown"
    )

    owner_caption = (
        "💰 <b>NEW PAYMENT REQUEST</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"🧾 <b>Payment ID:</b>\n"
        f"<code>#{payment.id}</code>\n\n"

        f"👤 <b>User:</b>\n"
        f"{display_name}\n\n"

        f"🔗 <b>Username:</b>\n"
        f"{display_username}\n\n"

        f"🆔 <b>Telegram ID:</b>\n"
        f"<code>{telegram_id}</code>\n\n"

        f"💰 <b>Amount:</b>\n"
        f"<b>{format_money(amount)}</b>\n\n"

        "📸 <b>Payment Screenshot Attached Above</b>\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "Choose an action below:"
    )

    # --------------------------------------------------------
    # Send to EVERY configured owner
    # --------------------------------------------------------

    owner_ids = settings.owner_ids

    if not owner_ids:
        logger.error(
            "OWNER_IDS is empty. Payment #%s cannot be reviewed.",
            payment.id,
        )

        await message.answer(
            "⚠️ Payment submitted, but owner notification "
            "configuration is missing."
        )

        return

    notification_success = False

    for owner_id in owner_ids:

        try:
            sent_message = await bot.send_photo(
                chat_id=owner_id,
                photo=screenshot_file_id,
                caption=owner_caption,
                reply_markup=payment_review_keyboard(
                    payment.id
                ),
                parse_mode="HTML",
            )

            notification_success = True

            logger.info(
                "Payment #%s sent to owner %s. "
                "User=%s Amount=%s Message=%s",
                payment.id,
                owner_id,
                telegram_id,
                amount,
                sent_message.message_id,
            )

        except Exception as e:

            logger.exception(
                "FAILED to send payment #%s to owner %s: %s",
                payment.id,
                owner_id,
                e,
            )

    # --------------------------------------------------------
    # If NO owner received it
    # --------------------------------------------------------

    if not notification_success:

        logger.error(
            "Payment #%s was created but NO OWNER received it.",
            payment.id,
        )

        try:
            await message.answer(
                "⚠️ <b>Payment Saved</b>\n\n"
                f"Payment ID: <code>#{payment.id}</code>\n"
                f"Amount: <b>{format_money(amount)}</b>\n\n"
                "❌ Owner notification failed.\n"
                "Please contact support.",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ============================================================
# APPROVE PAYMENT
# ============================================================

@router.callback_query(
    F.data.startswith("payment:approve:")
)
async def approve_payment(
    callback: CallbackQuery,
    bot: Bot,
):
    # --------------------------------------------------------
    # Owner check
    # --------------------------------------------------------

    if not is_owner(callback.from_user.id):
        await callback.answer(
            "⛔ Owner only",
            show_alert=True,
        )
        return

    # --------------------------------------------------------
    # Payment ID
    # --------------------------------------------------------

    try:
        payment_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "❌ Invalid payment.",
            show_alert=True,
        )
        return

    # --------------------------------------------------------
    # Approve in database
    # --------------------------------------------------------

    try:
        async with async_session_maker() as session:

            service = PaymentService(session)

            payment, user = await service.approve_payment(
                payment_id=payment_id,
                reviewer_id=callback.from_user.id,
            )

    except ValueError as e:
        await callback.answer(
            str(e),
            show_alert=True,
        )
        return

    except Exception:
        logger.exception(
            "Error approving payment #%s",
            payment_id,
        )

        await callback.answer(
            "❌ Approval failed.",
            show_alert=True,
        )
        return

    # --------------------------------------------------------
    # Update owner message
    # --------------------------------------------------------

    try:

        old_caption = (
            callback.message.caption
            or "💰 PAYMENT"
        )

        new_caption = (
            old_caption
            + "\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>APPROVED</b>\n"
            f"👮 Owner ID: <code>{callback.from_user.id}</code>"
        )

        await callback.message.edit_caption(
            caption=new_caption,
            reply_markup=None,
            parse_mode="HTML",
        )

    except Exception:
        logger.exception(
            "Could not edit owner payment message #%s",
            payment_id,
        )

    await callback.answer(
        "✅ Payment Approved"
    )

    # --------------------------------------------------------
    # Notify EXACT USER
    # --------------------------------------------------------

    try:

        await bot.send_message(
            chat_id=user.telegram_id,
            text=(
                "✅ <b>PAYMENT APPROVED</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"🧾 Payment ID: <code>#{payment.id}</code>\n"
                f"💰 Amount: <b>{format_money(payment.amount)}</b>\n\n"
                "💳 Amount has been added to your wallet.\n\n"
                f"💵 Current Balance: "
                f"<b>{format_money(user.balance)}</b>"
            ),
            parse_mode="HTML",
        )

    except Exception:
        logger.exception(
            "Could not notify user %s after approval.",
            user.telegram_id,
        )


# ============================================================
# REJECT PAYMENT
# ============================================================

@router.callback_query(
    F.data.startswith("payment:reject:")
)
async def reject_payment(
    callback: CallbackQuery,
    bot: Bot,
):
    # --------------------------------------------------------
    # Owner check
    # --------------------------------------------------------

    if not is_owner(callback.from_user.id):
        await callback.answer(
            "⛔ Owner only",
            show_alert=True,
        )
        return

    # --------------------------------------------------------
    # Payment ID
    # --------------------------------------------------------

    try:
        payment_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "❌ Invalid payment.",
            show_alert=True,
        )
        return

    # --------------------------------------------------------
    # Reject payment
    # --------------------------------------------------------

    try:

        async with async_session_maker() as session:

            service = PaymentService(session)

            payment = await service.reject_payment(
                payment_id=payment_id,
                reviewer_id=callback.from_user.id,
            )

            # Get EXACT user connected to this payment
            result = await session.execute(
                select(User).where(
                    User.id == payment.user_id
                )
            )

            user = result.scalar_one_or_none()

    except ValueError as e:
        await callback.answer(
            str(e),
            show_alert=True,
        )
        return

    except Exception:
        logger.exception(
            "Error rejecting payment #%s",
            payment_id,
        )

        await callback.answer(
            "❌ Rejection failed.",
            show_alert=True,
        )
        return

    # --------------------------------------------------------
    # Update owner message
    # --------------------------------------------------------

    try:

        old_caption = (
            callback.message.caption
            or "💰 PAYMENT"
        )

        new_caption = (
            old_caption
            + "\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"❌ <b>REJECTED</b>\n"
            f"👮 Owner ID: <code>{callback.from_user.id}</code>"
        )

        await callback.message.edit_caption(
            caption=new_caption,
            reply_markup=None,
            parse_mode="HTML",
        )

    except Exception:
        logger.exception(
            "Could not edit rejected payment #%s",
            payment_id,
        )

    await callback.answer(
        "❌ Payment Rejected"
    )

    # --------------------------------------------------------
    # Notify EXACT USER
    # --------------------------------------------------------

    if user:

        try:

            await bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    "❌ <b>PAYMENT REJECTED</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n\n"
                    f"🧾 Payment ID: <code>#{payment.id}</code>\n"
                    f"💰 Amount: <b>{format_money(payment.amount)}</b>\n\n"
                    "Your payment was rejected.\n\n"
                    f"📞 Support: {settings.SUPPORT_USERNAME}"
                ),
                parse_mode="HTML",
            )

        except Exception:
            logger.exception(
                "Could not notify rejected user %s",
                user.telegram_id,
    )
