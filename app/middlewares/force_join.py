from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject

from config import settings
from app.utils.logger import logger


class ForceJoinMiddleware(BaseMiddleware):
    """
    Force user to join required channels before using the bot.
    """

    CHANNELS = [
        settings.FORCE_JOIN_1,
        settings.FORCE_JOIN_2,
        settings.FORCE_JOIN_3,
    ]

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user

        if user is None:
            return await handler(event, data)

        # Owners ko skip kar do
        if user.id in settings.owner_ids:
            return await handler(event, data)

        bot: Bot = data.get("bot")
        if not bot:
            return await handler(event, data)

        # Check membership
        not_joined = []
        for channel in self.CHANNELS:
            try:
                member = await bot.get_chat_member(chat_id=channel, user_id=user.id)
                if member.status in (
                    ChatMemberStatus.LEFT,
                    ChatMemberStatus.KICKED,
                    ChatMemberStatus.RESTRICTED,
                ):
                    not_joined.append(channel)
            except Exception as e:
                logger.warning("ForceJoin check failed for %s: %s", channel, e)
                not_joined.append(channel)

        if not not_joined:
            # Sab channels join kiye hue hain
            return await handler(event, data)

        # Access deny + join buttons dikhao
        text = (
            "🔒 <b>ACCESS REQUIRED</b>\n\n"
            "Please join all required channels to use the bot."
        )

        buttons = []
        for i, channel in enumerate(self.CHANNELS, start=1):
            buttons.append([
                InlineKeyboardButton(
                    text=f"📢 Channel {i}",
                    url=f"https://t.me/{channel.lstrip('@')}"
                )
            ])

        buttons.append([
            InlineKeyboardButton(text="✅ Check Membership", callback_data="force_join:check")
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        if isinstance(event, Message):
            await event.answer(text, reply_markup=keyboard, parse_mode="HTML")
        elif isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            await event.answer()

        return None
