import os
import time
from pathlib import Path

from src.bot.services.file_cleaner import sweep_once


def test_sweep_removes_old_files(tmp_path: Path) -> None:
    # Arrange
    chat_dir = tmp_path / "42"
    chat_dir.mkdir()
    old = chat_dir / "old.jpg"
    fresh = chat_dir / "fresh.jpg"
    old.write_bytes(b"x")
    fresh.write_bytes(b"y")
    # Backdate old file by 10 days.
    past = time.time() - 10 * 86400
    os.utime(old, (past, past))

    # Act
    removed = sweep_once(tmp_path, max_age_days=7)

    # Assert
    assert removed == 1
    assert not old.exists()
    assert fresh.exists()


def test_sweep_no_op_when_disabled(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "a.jpg").write_bytes(b"x")

    # Act
    removed = sweep_once(tmp_path, max_age_days=0)

    # Assert
    assert removed == 0
    assert (tmp_path / "a.jpg").exists()


def test_sweep_handles_missing_root(tmp_path: Path) -> None:
    # Arrange
    missing = tmp_path / "does_not_exist"

    # Act
    removed = sweep_once(missing, max_age_days=7)

    # Assert
    assert removed == 0
