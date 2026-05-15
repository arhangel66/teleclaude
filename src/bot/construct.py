from pathlib import Path

from aiogram import Bot

from src.bot.config import Settings
from src.bot.services.agent_runner import AgentRunner
from src.bot.services.cli_backends import ClaudeCliBackend, CodexCliBackend
from src.bot.services.file_cleaner import FileCleaner
from src.bot.services.scheduler import TaskScheduler, load_tasks
from src.bot.services.session_store import SessionStore
from src.bot.services.telegram_ui import TelegramUI
from src.bot.services.transcriber import Transcriber

settings = Settings()

bot = Bot(token=settings.telegram_bot_token)
session_store = SessionStore(db_path=settings.sqlite_db)

if settings.agent_backend == "codex":
    backend = CodexCliBackend(
        codex_binary=settings.codex_binary,
        working_directory=settings.working_directory,
    )
else:
    backend = ClaudeCliBackend(claude_binary=settings.claude_binary)

agent_runner = AgentRunner(
    backend=backend,
    working_directory=settings.working_directory,
)
claude_runner = agent_runner
telegram_ui = TelegramUI(bot=bot)
transcriber = Transcriber(api_key=settings.openrouter_api_key, model=settings.stt_model)

task_scheduler = TaskScheduler(
    tasks=load_tasks(Path("scheduled_tasks.yaml")),
    settings=settings,
    claude_runner=agent_runner,
    session_store=session_store,
    ui=telegram_ui,
)
file_cleaner = FileCleaner(
    root=Path("files"),
    max_age_days=settings.file_retention_days,
)
