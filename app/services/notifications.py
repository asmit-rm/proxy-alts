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
