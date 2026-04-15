from pathlib import Path

from aiogram import Bot

from src.bot.config import Settings
from src.bot.services.claude_runner import ClaudeRunner
from src.bot.services.scheduler import TaskScheduler, load_tasks
from src.bot.services.session_store import SessionStore
from src.bot.services.telegram_ui import TelegramUI
from src.bot.services.transcriber import Transcriber

settings = Settings()

bot = Bot(token=settings.telegram_bot_token)
session_store = SessionStore(db_path=settings.sqlite_db)
claude_runner = ClaudeRunner(
    claude_binary=settings.claude_binary,
    working_directory=settings.working_directory,
)
telegram_ui = TelegramUI(bot=bot)
transcriber = Transcriber(api_key=settings.openrouter_api_key, model=settings.stt_model)

task_scheduler = TaskScheduler(
    tasks=load_tasks(Path("scheduled_tasks.yaml")),
    settings=settings,
    claude_runner=claude_runner,
    session_store=session_store,
    ui=telegram_ui,
)
