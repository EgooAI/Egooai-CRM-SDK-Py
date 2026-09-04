from typing import Optional

from models import Message

from .base import BaseManager


class MessageManager(BaseManager[Message]):
    """负责 Message 表的连接初始化与增删改查操作。"""

    model = Message
    pk_field = "external_mid"
    editable_fields = ("sid", "sender", "read", "content", "type", "created_at")
    pk_is_auto = False

    def add_message(self, message: Message) -> None:
        self._add(message)

    def upsert_message(self, message: Message) -> None:
        self._upsert(message)

    def delete_message(self, external_mid: str) -> None:
        self._delete(external_mid)

    def edit_message(self, external_mid: str, message: Message) -> None:
        self._edit(external_mid, message)

    def get_message(self, external_mid: str) -> Optional[Message]:
        return self._get(external_mid)

    def list_message(self) -> list[Message]:
        return self._list()


__all__ = ["MessageManager"]
