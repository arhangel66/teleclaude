import pytest
from pydantic import ValidationError

from src.bot.config import Settings


def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "123")
    monkeypatch.setenv("WORKING_DIRECTORY", "/tmp")


def test_agent_backend_defaults_to_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    _set_required_env(monkeypatch)
    monkeypatch.delenv("AGENT_BACKEND", raising=False)

    # Act
    settings = Settings(_env_file=None)

    # Assert
    assert settings.agent_backend == "claude"


def test_agent_backend_accepts_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    _set_required_env(monkeypatch)
    monkeypatch.setenv("AGENT_BACKEND", "codex")

    # Act
    settings = Settings(_env_file=None)

    # Assert
    assert settings.agent_backend == "codex"


def test_agent_backend_rejects_unknown_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    _set_required_env(monkeypatch)
    monkeypatch.setenv("AGENT_BACKEND", "unknown")

    # Act / Assert
    with pytest.raises(ValidationError, match="agent_backend"):
        Settings(_env_file=None)
