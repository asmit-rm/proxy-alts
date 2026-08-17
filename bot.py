import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.database.database import init_db
from app.handlers.start import router as start_router
from app.handlers.shop import router as shop_router
from app.middlewares.force_join import ForceJoinMiddleware
from app.utils.logger import logger
from config import settings


async def main() -> None:
    logger.info("Starting Proxy Manager bot...")

    # Initialize database tables
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        sys.exit(1)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Middlewares
    dp.message.middleware(ForceJoinMiddleware())
    dp.callback_query.middleware(ForceJoinMiddleware())

    # Register routers
    dp.include_router(start_router)
    dp.include_router(shop_router)

    logger.info("Bot is running. Owner IDs: %s", settings.owner_ids)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
