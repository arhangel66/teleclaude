import aiosqlite


class SessionStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS sessions "
            "(chat_id INTEGER PRIMARY KEY, session_id TEXT NOT NULL)"
        )
        await self._db.commit()

    async def get(self, chat_id: int) -> str | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT session_id FROM sessions WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set(self, chat_id: int, session_id: str) -> None:
        assert self._db is not None
        await self._db.execute(
            "INSERT INTO sessions (chat_id, session_id) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET session_id = excluded.session_id",
            (chat_id, session_id),
        )
        await self._db.commit()

    async def list_chats(self) -> list[int]:
        assert self._db is not None
        async with self._db.execute(
            "SELECT chat_id FROM sessions WHERE session_id != '' ORDER BY chat_id"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def reset(self, chat_id: int) -> None:
        assert self._db is not None
        await self._db.execute("DELETE FROM sessions WHERE chat_id = ?", (chat_id,))
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
