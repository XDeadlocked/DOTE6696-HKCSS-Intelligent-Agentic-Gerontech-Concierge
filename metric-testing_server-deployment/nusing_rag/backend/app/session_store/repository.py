from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging

from app.core.exceptions import SessionNotFoundError
from app.schemas.session import SessionState

logger = logging.getLogger(__name__)


class SessionRepository(ABC):
    @abstractmethod
    def get(self, session_id: str) -> SessionState: ...

    @abstractmethod
    def save(self, state: SessionState) -> None: ...

    @abstractmethod
    def delete(self, session_id: str) -> None: ...

    @abstractmethod
    def touch(self, session_id: str) -> None: ...

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def clear(self) -> None: ...

    @abstractmethod
    def get_all_for_persistence(self) -> list[SessionState]: ...


class InMemorySessionRepository(SessionRepository):
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, SessionState] = {}

    def _is_expired(self, state: SessionState) -> bool:
        return datetime.now(timezone.utc) - state.updated_at > timedelta(
            seconds=self.ttl_seconds
        )

    def get(self, session_id: str) -> SessionState:
        state = self._store.get(session_id)
        if state is None or self._is_expired(state):
            self._store.pop(session_id, None)
            raise SessionNotFoundError(session_id)
        return state

    def save(self, state: SessionState) -> None:
        self._store[state.session_id] = state

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    def touch(self, session_id: str) -> None:
        state = self.get(session_id)
        state.updated_at = datetime.now(timezone.utc)
        self.save(state)

    def count(self) -> int:
        expired = [
            session_id
            for session_id, state in self._store.items()
            if self._is_expired(state)
        ]
        for session_id in expired:
            self._store.pop(session_id, None)
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()

    def get_all_for_persistence(self) -> list[SessionState]:
        self._purge_expired()
        return list(self._store.values())

    def _purge_expired(self) -> None:
        expired = [
            session_id
            for session_id, state in self._store.items()
            if self._is_expired(state)
        ]
        for session_id in expired:
            self._store.pop(session_id, None)


class SQLitePersistenceStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
                ON sessions(updated_at)
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save(self, state: SessionState) -> None:
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions (session_id, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    state.session_id,
                    state.model_dump_json(),
                    state.created_at.isoformat(),
                    state.updated_at.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save_batch(self, states: list[SessionState]) -> None:
        conn = self._get_connection()
        try:
            rows = [
                (
                    s.session_id,
                    s.model_dump_json(),
                    s.created_at.isoformat(),
                    s.updated_at.isoformat(),
                )
                for s in states
            ]
            conn.executemany(
                """
                INSERT OR REPLACE INTO sessions (session_id, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        finally:
            conn.close()

    def delete(self, session_id: str) -> None:
        conn = self._get_connection()
        try:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()

    def count(self) -> int:
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()


class MemoryCleanupScheduler:
    def __init__(
        self,
        repository: InMemorySessionRepository,
        persistence: SQLitePersistenceStore | None = None,
        hour: int = 3,
        minute: int = 0,
    ) -> None:
        self._repository = repository
        self._persistence = persistence
        self._hour = hour
        self._minute = minute
        self._task: asyncio.Task | None = None

    def _seconds_until_next(self) -> float:
        now = datetime.now()
        target = now.replace(hour=self._hour, minute=self._minute, second=0, microsecond=0)
        if target <= now:
            target = target + timedelta(days=1)
        return (target - now).total_seconds()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())
        logger.info(
            "Memory cleanup scheduler started (daily at %02d:%02d)",
            self._hour,
            self._minute,
        )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Memory cleanup scheduler stopped")

    async def _run(self) -> None:
        while True:
            seconds = self._seconds_until_next()
            logger.info(
                "Next memory cleanup in %.0f seconds (at %02d:%02d)",
                seconds,
                self._hour,
                self._minute,
            )
            await asyncio.sleep(seconds)
            await self.cleanup_now()

    async def cleanup_now(self) -> None:
        try:
            states = self._repository.get_all_for_persistence()
            count = len(states)
            if count > 0 and self._persistence:
                self._persistence.save_batch(states)
                logger.info("Flushed %d sessions to SQLite before memory cleanup", count)
            self._repository.clear()
            logger.info("Memory cleanup completed: cleared %d sessions", count)
        except Exception:
            logger.exception("Memory cleanup failed")
