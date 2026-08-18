from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.database.database import async_session_maker
from app.database.models import WalletTransactionType
from app.keyboards.wallet import wallet_keyboard, deposit_keyboard
from app.keyboards.home import home_keyboard
from app.services.wallet import WalletService
from app.services.users import UserService
from app.utils.helpers import format_money
from app.utils.validators import is_owner
from app.utils.logger import logger
from config import settings

router = Router(name="wallet")


@router.callback_query(F.data == "wallet:balance")
async def show_balance(callback: CallbackQuery):
    async with async_session_maker() as session:
        service = WalletService(session)
        balance = await service.get_balance(callback.from_user.id)

    text = (
        f"💳 <b>YOUR WALLET</b>\n\n"
        f"Balance: <b>{format_money(balance)}</b>"
    )

    await callback.message.edit_text(text, reply_markup=wallet_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "wallet:history")
async def show_history(callback: CallbackQuery):
    async with async_session_maker() as session:
        service = WalletService(session)
        transactions = await service.get_transactions(callback.from_user.id, limit=10)

    if not transactions:
        text = "📜 <b>Transaction History</b>\n\nNo transactions yet."
    else:
        lines = ["📜 <b>Transaction History</b>\n"]
        for tx in transactions:
            sign = "+" if tx.type in (
                WalletTransactionType.DEPOSIT,
                WalletTransactionType.ADMIN_CREDIT,
                WalletTransactionType.REFUND,
            ) else "-"
            lines.append(
                f"{sign}{format_money(tx.amount)} | {tx.type.value}\n"
                f"<i>{tx.created_at.strftime('%d %b %Y %H:%M')}</i>"
            )
        text = "\n\n".join(lines)

    await callback.message.edit_text(text, reply_markup=wallet_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "wallet:deposit")
async def deposit_info(callback: CallbackQuery):
    text = (
        f"💳 <b>DEPOSIT</b>\n\n"
        f"UPI ID:\n<code>{settings.UPI_ID}</code>\n\n"
        f"Send payment and submit screenshot.\n"
        f"(Deposit system coming in next stage)"
    )

    await callback.message.edit_text(text, reply_markup=deposit_keyboard(), parse_mode="HTML")
    await callback.answer()


# ==================== OWNER COMMANDS ====================

@router.message(Command("give"))
async def cmd_give(message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        await message.answer("⛔ Access denied. Owner only.")
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer("Usage: /give <userid> <amount>\nExample: /give 123456789 500")
        return

    try:
        target_id = int(args[1])
        amount = Decimal(args[2])
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except (ValueError, InvalidOperation):
        await message.answer("❌ Invalid userid or amount.")
        return

    async with async_session_maker() as session:
        try:
            service = WalletService(session)
            user, tx = await service.credit(
                telegram_id=target_id,
                amount=amount,
                tx_type=WalletTransactionType.ADMIN_CREDIT,
                description=f"Admin credit by {message.from_user.id}",
                created_by=message.from_user.id,
            )
        except ValueError as e:
            await message.answer(f"❌ {e}")
            return

    await message.answer(
        f"✅ <b>BALANCE UPDATED</b>\n\n"
        f"User ID: <code>{target_id}</code>\n"
        f"Added: <b>{format_money(amount)}</b>\n"
        f"New Balance: <b>{format_money(user.balance)}</b>",
        parse_mode="HTML"
    )

    # Notify user
    try:
        await message.bot.send_message(
            chat_id=target_id,
            text=(
                f"💰 <b>BALANCE CREDITED</b>\n\n"
                f"{format_money(amount)} has been added to your wallet.\n\n"
                f"💳 Current Balance: <b>{format_money(user.balance)}</b>"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning("Could not notify user %s: %s", target_id, e)


@router.message(Command("take"))
async def cmd_take(message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        await message.answer("⛔ Access denied. Owner only.")
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer("Usage: /take <userid> <amount>\nExample: /take 123456789 100")
        return

    try:
        target_id = int(args[1])
        amount = Decimal(args[2])
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except (ValueError, InvalidOperation):
        await message.answer("❌ Invalid userid or amount.")
        return

    async with async_session_maker() as session:
        try:
            service = WalletService(session)
            user, tx = await service.debit(
                telegram_id=target_id,
                amount=amount,
                tx_type=WalletTransactionType.ADMIN_DEBIT,
                description=f"Admin debit by {message.from_user.id}",
                created_by=message.from_user.id,
            )
        except ValueError as e:
            await message.answer(f"❌ {e}")
            return

    await message.answer(
        f"✅ <b>BALANCE UPDATED</b>\n\n"
        f"User ID: <code>{target_id}</code>\n"
        f"Deducted: <b>{format_money(amount)}</b>\n"
        f"New Balance: <b>{format_money(user.balance)}</b>",
        parse_mode="HTML"
    )

    try:
        await message.bot.send_message(
            chat_id=target_id,
            text=(
                f"💸 <b>BALANCE DEBITED</b>\n\n"
                f"{format_money(amount)} has been deducted from your wallet.\n\n"
                f"💳 Current Balance: <b>{format_money(user.balance)}</b>"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning("Could not notify user %s: %s", target_id, e)
