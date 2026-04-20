import asyncio
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_SECONDS_PER_DAY = 86400


def sweep_once(root: Path, max_age_days: int, now: float | None = None) -> int:
    """Remove files under `root` whose mtime is older than `max_age_days`.

    Returns the number of files removed. Silently ignores missing root.
    """
    if max_age_days <= 0 or not root.exists():
        return 0
    cutoff = (now if now is not None else time.time()) - max_age_days * _SECONDS_PER_DAY
    removed = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError as exc:
            logger.warning("file_cleaner: failed to remove %s: %s", path, exc)
    return removed


class FileCleaner:
    """Periodically deletes old files from the attachments directory."""

    def __init__(
        self,
        root: Path,
        max_age_days: int,
        interval_seconds: int = _SECONDS_PER_DAY,
    ) -> None:
        self._root = root
        self._max_age_days = max_age_days
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._max_age_days <= 0:
            logger.info("file_cleaner disabled (file_retention_days=%d)", self._max_age_days)
            return
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="file-cleaner")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                removed = sweep_once(self._root, self._max_age_days)
                if removed:
                    logger.info("file_cleaner removed %d old files", removed)
            except Exception:
                logger.exception("file_cleaner sweep failed")
            await asyncio.sleep(self._interval)
