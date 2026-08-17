from pathlib import Path
from typing import Optional

from sqlalchemy import inspect
from sqlmodel import Session, select

from models.session_meta import SessionMeta
from utils.common import bootstrap_engine, get_database_lock


class SessionMetaManager:
    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        self.database_path, self.engine = bootstrap_engine(database_path)
        self._lock = get_database_lock(self.database_path)

    @staticmethod
    def _payload_tuple(session_meta: SessionMeta) -> tuple[object, ...]:
        return (session_meta.key, session_meta.name, session_meta.participants)

    @staticmethod
    def _sync_session_meta_state(target: SessionMeta, source: SessionMeta) -> None:
        target.sid = source.sid

    @staticmethod
    def _apply_session_meta_updates(current_session_meta: SessionMeta, session_meta: SessionMeta) -> None:
        current_session_meta.key = session_meta.key
        current_session_meta.name = session_meta.name
        current_session_meta.participants = session_meta.participants

    def _find_matching_session_meta(self, session: Session, session_meta: SessionMeta) -> Optional[SessionMeta]:
        if not session_meta.key:
            return None
        statement = select(SessionMeta).where(SessionMeta.key == session_meta.key)
        return session.exec(statement).first()

    def add_session_meta(self, session_meta: SessionMeta) -> None:
        with self._lock:
            with Session(self.engine) as session:
                session.add(session_meta)
                session.commit()
                session.refresh(session_meta)

    def upsert_session_meta(self, session_meta: SessionMeta) -> None:
        with self._lock:
            with Session(self.engine) as session:
                if session_meta.sid is not None:
                    current_session_meta = session.get(SessionMeta, session_meta.sid)
                    if current_session_meta is None:
                        raise ValueError(f"SessionMeta {session_meta.sid} not found")

                    if self._payload_tuple(current_session_meta) == self._payload_tuple(session_meta):
                        self._sync_session_meta_state(session_meta, current_session_meta)
                        return

                    self._apply_session_meta_updates(current_session_meta, session_meta)
                    session.add(current_session_meta)
                    session.commit()
                    session.refresh(current_session_meta)
                    self._sync_session_meta_state(session_meta, current_session_meta)
                    return

                existing_session_meta = self._find_matching_session_meta(session, session_meta)
                if existing_session_meta is not None:
                    self._sync_session_meta_state(session_meta, existing_session_meta)
                    return

                session.add(session_meta)
                session.commit()
                session.refresh(session_meta)

    def delete_session_meta(self, sid: int) -> None:
        with self._lock:
            with Session(self.engine) as session:
                current_session_meta = session.get(SessionMeta, sid)
                if current_session_meta is None:
                    return

                session.delete(current_session_meta)
                session.commit()

    def edit_session_meta(self, sid: int, session_meta: SessionMeta) -> None:
        with self._lock:
            with Session(self.engine) as session:
                current_session_meta = session.get(SessionMeta, sid)
                if current_session_meta is None:
                    raise ValueError(f"SessionMeta {sid} not found")

                self._apply_session_meta_updates(current_session_meta, session_meta)

                session.add(current_session_meta)
                session.commit()
                session.refresh(current_session_meta)

    def get_session_meta(self, sid: int) -> Optional[SessionMeta]:
        with Session(self.engine) as session:
            return session.get(SessionMeta, sid)

    def list_session_meta(self) -> list[SessionMeta]:
        with Session(self.engine) as session:
            sid_column = inspect(SessionMeta).columns.sid
            statement = select(SessionMeta).order_by(sid_column)
            return list(session.exec(statement).all())


__all__ = ["SessionMetaManager"]
