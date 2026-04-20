import asyncio
import logging

from aiogram import Dispatcher

from src.bot.construct import bot, file_cleaner, session_store, task_scheduler
from src.bot.handlers import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("src.bot").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)


async def main() -> None:
    await session_store.init()
    task_scheduler.start()
    file_cleaner.start()

    dp = Dispatcher()
    dp.include_router(router)

    logger.info("Starting bot...")
    logger.info("Bot started polling")
    try:
        await dp.start_polling(bot)
    finally:
        await file_cleaner.stop()
        await task_scheduler.stop()
        await session_store.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
