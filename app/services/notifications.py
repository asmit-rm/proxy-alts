from aiogram import Bot

from config import settings
from app.utils.helpers import format_money
from app.utils.logger import logger


class NotificationService:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def notify_owners_new_sale(
        self,
        order_id: int,
        buyer_telegram_id: int,
        buyer_username: str | None,
        country: str,
        quality: str,
        product_name: str,
        number: str | None,
        amount,
    ):
        username = f"@{buyer_username}" if buyer_username else "No username"

        text = (
            f"🛒 <b>NEW SALE</b>\n\n"
            f"📦 Order ID: <code>#{order_id}</code>\n"
            f"👤 User: {username}\n"
            f"🆔 Telegram ID: <code>{buyer_telegram_id}</code>\n\n"
            f"🌍 {country} | 💎 {quality}\n"
            f"📝 {product_name}\n"
            f"📱 Number: <code>{number or 'N/A'}</code>\n"
            f"💰 Amount: <b>{format_money(amount)}</b>"
        )

        for owner_id in settings.owner_ids:
            try:
                await self.bot.send_message(
                    chat_id=owner_id,
                    text=text,
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning("Could not notify owner %s about sale: %s", owner_id, e)

        # Public / group sales log
        await self.notify_sales_channel(
            buyer_telegram_id=buyer_telegram_id,
            country=country,
            quality=quality,
            product_name=product_name,
            number=number,
        )

    async def notify_sales_channel(
        self,
        buyer_telegram_id: int,
        country: str,
        quality: str,
        product_name: str,
        number: str | None,
    ):
        chat_id = getattr(settings, "SALES_LOG_CHAT_ID", None)
        if not chat_id:
            return

        # Mask user id: 72***963
        uid = str(buyer_telegram_id)
        if len(uid) > 5:
            uid_masked = uid[:2] + "***" + uid[-3:]
        else:
            uid_masked = uid

        # Mask number: 959****73
        masked = number
        if number and len(number) > 6:
            masked = number[:3] + "****" + number[-2:]

        text = (
            f"💠 <b>NEW ACCOUNT SOLD</b> 💠\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 User: <code>{uid_masked}</code>\n"
            f"📦 Item: {country} ({quality})\n"
            f"📍 Region: {country}\n"
            f"📱 Number: <code>{masked or 'N/A'}</code>\n"
            f"⚡ Status: Verified & Delivered\n\n"
            f"🤖 Always use the @TeleVNumStorebot"
        )

        try:
            await self.bot.send_message(
                chat_id=int(chat_id),
                text=text,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Sales channel log failed: %s", e)
