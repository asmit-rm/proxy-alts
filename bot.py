import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.database.database import init_db
from app.handlers.start import router as start_router
from app.handlers.shop import router as shop_router
from app.handlers.wallet import router as wallet_router
from app.handlers.payments import router as payments_router
from app.handlers.orders import router as orders_router
from app.handlers.admin import router as admin_router
from app.handlers.support import router as support_router
from app.middlewares.force_join import ForceJoinMiddleware
from app.utils.logger import logger
from config import settings


async def main() -> None:
    logger.info("Starting Proxy Manager bot...")

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

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Middlewares
    dp.message.middleware(ForceJoinMiddleware())
    dp.callback_query.middleware(ForceJoinMiddleware())

    # Register routers
    dp.include_router(start_router)
    dp.include_router(shop_router)
    dp.include_router(wallet_router)
    dp.include_router(payments_router)
    dp.include_router(orders_router)
    dp.include_router(admin_router)
    dp.include_router(support_router)

    logger.info("Bot is running. Owner IDs: %s", settings.owner_ids)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
