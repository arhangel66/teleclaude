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
