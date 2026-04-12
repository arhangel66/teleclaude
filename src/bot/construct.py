from aiogram import Bot

from src.bot.config import Settings
from src.bot.services.claude_runner import ClaudeRunner
from src.bot.services.session_store import SessionStore
from src.bot.services.telegram_ui import TelegramUI

settings = Settings()

bot = Bot(token=settings.telegram_bot_token)
session_store = SessionStore(db_path=settings.sqlite_db)
claude_runner = ClaudeRunner(
    claude_binary=settings.claude_binary,
    working_directory=settings.working_directory,
)
telegram_ui = TelegramUI(bot=bot)
