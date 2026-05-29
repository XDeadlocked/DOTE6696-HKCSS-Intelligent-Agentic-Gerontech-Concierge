from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import logging

from app.core.config import Settings
from app.schemas.session import SessionState
from app.session_store.repository import (
    InMemorySessionRepository,
    SessionRepository,
    SQLitePersistenceStore,
    MemoryCleanupScheduler,
)

logger = logging.getLogger(__name__)


class SessionStoreService:
    def __init__(
        self,
        repository: SessionRepository,
        persistence: SQLitePersistenceStore | None = None,
        ttl_seconds: int = 7200,
    ) -> None:
        self.repository = repository
        self.persistence = persistence
        self.ttl_seconds = ttl_seconds

    def create_session(self, session_id: str | None = None) -> SessionState:
        state = SessionState.new(session_id)
        self.repository.save(state)
        if self.persistence:
            self.persistence.save(state)
        return state

    def get_session(self, session_id: str) -> SessionState:
        return self.repository.get(session_id)

    def save_session(self, state: SessionState) -> None:
        state.updated_at = datetime.now(timezone.utc)
        self.repository.save(state)
        if self.persistence:
            self.persistence.save(state)

    def delete_session(self, session_id: str) -> None:
        self.repository.delete(session_id)
        if self.persistence:
            self.persistence.delete(session_id)

    def touch_session(self, session_id: str) -> None:
        self.repository.touch(session_id)

    def bind_websocket(
        self,
        session_id: str,
        channel: str,
        connection_id: str,
    ) -> None:
        state = self.get_session(session_id)
        bindings = state.websocket_bindings.setdefault(channel, [])
        if connection_id not in bindings:
            bindings.append(connection_id)
        self.save_session(state)

    def unbind_websocket(
        self,
        session_id: str,
        channel: str,
        connection_id: str,
    ) -> None:
        state = self.get_session(session_id)
        bindings = state.websocket_bindings.get(channel, [])
        if connection_id in bindings:
            bindings.remove(connection_id)
        if not bindings:
            state.websocket_bindings.pop(channel, None)
        self.save_session(state)

    def count_active_sessions(self) -> int:
        return self.repository.count()

    def flush_all_to_persistence(self) -> int:
        if not self.persistence:
            return 0
        if not isinstance(self.repository, InMemorySessionRepository):
            return 0
        states = self.repository.get_all_for_persistence()
        if states:
            self.persistence.save_batch(states)
        return len(states)


def build_session_store(settings: Settings) -> SessionStoreService:
    ttl_seconds = settings.session_ttl_minutes * 60
    repository = InMemorySessionRepository(ttl_seconds)

    persistence = SQLitePersistenceStore(settings.session_sqlite_path)
    logger.info(
        "SQLite persistence enabled (path=%s)",
        settings.session_sqlite_path,
    )

    return SessionStoreService(
        repository=repository,
        persistence=persistence,
        ttl_seconds=ttl_seconds,
    )


def build_cleanup_scheduler(
    service: SessionStoreService,
    hour: int = 3,
    minute: int = 0,
) -> MemoryCleanupScheduler | None:
    repo = service.repository
    if not isinstance(repo, InMemorySessionRepository):
        logger.warning("Cleanup scheduler requires InMemorySessionRepository")
        return None
    return MemoryCleanupScheduler(
        repository=repo,
        persistence=service.persistence,
        hour=hour,
        minute=minute,
    )
