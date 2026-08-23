from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ChatMemberStatus

from app.database.database import async_session_maker
from app.keyboards.home import home_keyboard
from app.services.users import UserService
from app.utils.helpers import format_money
from app.utils.logger import logger
from config import settings

router = Router(name="start")

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not message.from_user:
        return

    user = message.from_user
    async with async_session_maker() as session:
        service = UserService(session)
        db_user, created = await service.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )

    balance_text = format_money(db_user.balance)

    text = (
        f"👋 Welcome to <b>Proxy Manager</b>!\n\n"
        f"💳 Balance: <b>{balance_text}</b>\n"
        f"🟢 Store Status: Online\n\n"
        f"📜 <b>Policy</b>\n"
        f"• All sales are <b>final and non-refundable</b>.\n"
        f"• If an account is frozen, banned, or limited — "
        f"that is <b>not our responsibility</b>.\n"
        f"• Refunds only in rare vital cases (admin decision). "
        f"Normal cases = <b>no refund</b>.\n"
        f"• Use accounts at your own risk."
    )

    # Welcome image + message
    await message.answer_photo(
        photo="https://files.catbox.moe/vc9lxz.jpg",
        caption=text,
        reply_markup=home_keyboard(),
        parse_mode="HTML",
    )

    if created:
        logger.info("New user registered: telegram_id=%s username=%s", user.id, user.username)
    else:
        logger.info("User started bot: telegram_id=%s", user.id)


@router.callback_query(F.data == "force_join:check")
async def check_force_join(callback: CallbackQuery):
    bot = callback.bot
    user_id = callback.from_user.id

    channels = [
        settings.FORCE_JOIN_1,
        settings.FORCE_JOIN_2,
        settings.FORCE_JOIN_3,
    ]

    not_joined = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in (
                ChatMemberStatus.LEFT,
                ChatMemberStatus.KICKED,
                ChatMemberStatus.RESTRICTED,
            ):
                not_joined.append(channel)
        except Exception:
            not_joined.append(channel)

    if not_joined:
        await callback.answer("❌ You still need to join all channels!", show_alert=True)
        return

    # Sab channels join kar liye → Home dikhao
    async with async_session_maker() as session:
        service = UserService(session)
        db_user, _ = await service.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )

    balance_text = format_money(db_user.balance)

    text = (
        f"👋 Welcome to <b>TG ALT STORE</b>!\n\n"
        f"💳 Balance: <b>{balance_text}</b>\n"
        f"🟢 Store Status: Online"
    )

    await callback.message.edit_text(text, reply_markup=home_keyboard(), parse_mode="HTML")
    await callback.answer("✅ Access granted!")
