from typing import Optional

from models import SessionMeta

from .base import BaseManager


class SessionMetaManager(BaseManager[SessionMeta]):
    """负责 SessionMeta 表的连接初始化与增删改查操作。"""

    model = SessionMeta
    pk_field = "sid"
    editable_fields = ("key", "name", "participants")
    match_fields = ("key",)
    adopt_on_key_match = True

    def add_session_meta(self, session_meta: SessionMeta) -> None:
        self._add(session_meta)

    def upsert_session_meta(self, session_meta: SessionMeta) -> None:
        self._upsert(session_meta)

    def delete_session_meta(self, sid: int) -> None:
        self._delete(sid)

    def edit_session_meta(self, sid: int, session_meta: SessionMeta) -> None:
        self._edit(sid, session_meta)

    def get_session_meta(self, sid: int) -> Optional[SessionMeta]:
        return self._get(sid)

    def list_session_meta(self) -> list[SessionMeta]:
        return self._list()


__all__ = ["SessionMetaManager"]
