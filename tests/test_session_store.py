from pathlib import Path

import pytest

from src.bot.services.session_store import SessionStore


@pytest.mark.asyncio
async def test_session_store_list_chats(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.db"
    store = SessionStore(db_path=str(db_path))
    await store.init()
    try:
        await store.set(30, "sess-c")
        await store.set(10, "sess-a")
        await store.set(20, "sess-b")

        chats = await store.list_chats()

        assert chats == [10, 20, 30]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_session_store_list_chats_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    store = SessionStore(db_path=str(db_path))
    await store.init()
    try:
        chats = await store.list_chats()

        assert chats == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_session_store_isolates_sessions_by_backend(tmp_path: Path) -> None:
    db_path = tmp_path / "backend_sessions.db"
    store = SessionStore(db_path=str(db_path))
    await store.init()
    try:
        await store.set(42, "claude-session", backend="claude")
        await store.set(42, "codex-thread", backend="codex")

        claude_session = await store.get(42, backend="claude")
        codex_session = await store.get(42, backend="codex")

        assert claude_session == "claude-session"
        assert codex_session == "codex-thread"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_session_store_reset_only_selected_backend(tmp_path: Path) -> None:
    db_path = tmp_path / "reset_backend.db"
    store = SessionStore(db_path=str(db_path))
    await store.init()
    try:
        await store.set(42, "claude-session", backend="claude")
        await store.set(42, "codex-thread", backend="codex")

        await store.reset(42, backend="codex")

        assert await store.get(42, backend="claude") == "claude-session"
        assert await store.get(42, backend="codex") is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_session_store_lists_chats_for_selected_backend(tmp_path: Path) -> None:
    db_path = tmp_path / "list_backend.db"
    store = SessionStore(db_path=str(db_path))
    await store.init()
    try:
        await store.set(10, "claude-session", backend="claude")
        await store.set(20, "codex-thread", backend="codex")
        await store.set(30, "codex-thread-2", backend="codex")

        chats = await store.list_chats(backend="codex")

        assert chats == [20, 30]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_session_store_migrates_existing_rows_to_claude(tmp_path: Path) -> None:
    import aiosqlite

    db_path = tmp_path / "legacy.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "CREATE TABLE sessions "
            "(chat_id INTEGER PRIMARY KEY, session_id TEXT NOT NULL)"
        )
        await db.execute(
            "INSERT INTO sessions (chat_id, session_id) VALUES (?, ?)",
            (42, "legacy-session"),
        )
        await db.commit()

    store = SessionStore(db_path=str(db_path))
    await store.init()
    try:
        assert await store.get(42, backend="claude") == "legacy-session"
        assert await store.get(42, backend="codex") is None
    finally:
        await store.close()
