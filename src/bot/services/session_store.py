import aiosqlite


class SessionStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._ensure_schema()
        await self._db.commit()

    async def _ensure_schema(self) -> None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'sessions'"
        ) as cursor:
            exists = await cursor.fetchone()

        if exists is None:
            await self._create_sessions_table()
            return

        async with self._db.execute("PRAGMA table_info(sessions)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]

        if "backend" in columns:
            return

        await self._db.execute("ALTER TABLE sessions RENAME TO sessions_legacy")
        await self._create_sessions_table()
        await self._db.execute(
            "INSERT INTO sessions (chat_id, backend, session_id) "
            "SELECT chat_id, 'claude', session_id FROM sessions_legacy"
        )
        await self._db.execute("DROP TABLE sessions_legacy")

    async def _create_sessions_table(self) -> None:
        assert self._db is not None
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS sessions "
            "(chat_id INTEGER NOT NULL, "
            "backend TEXT NOT NULL, "
            "session_id TEXT NOT NULL, "
            "PRIMARY KEY (chat_id, backend))"
        )

    async def get(self, chat_id: int, backend: str = "claude") -> str | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT session_id FROM sessions WHERE chat_id = ? AND backend = ?",
            (chat_id, backend),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set(
        self, chat_id: int, session_id: str, backend: str = "claude"
    ) -> None:
        assert self._db is not None
        await self._db.execute(
            "INSERT INTO sessions (chat_id, backend, session_id) VALUES (?, ?, ?) "
            "ON CONFLICT(chat_id, backend) "
            "DO UPDATE SET session_id = excluded.session_id",
            (chat_id, backend, session_id),
        )
        await self._db.commit()

    async def list_chats(self, backend: str = "claude") -> list[int]:
        assert self._db is not None
        async with self._db.execute(
            "SELECT chat_id FROM sessions "
            "WHERE backend = ? AND session_id != '' ORDER BY chat_id",
            (backend,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def reset(self, chat_id: int, backend: str = "claude") -> None:
        assert self._db is not None
        await self._db.execute(
            "DELETE FROM sessions WHERE chat_id = ? AND backend = ?",
            (chat_id, backend),
        )
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
