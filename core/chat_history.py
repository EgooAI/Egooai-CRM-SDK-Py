from typing import Optional

from models import ChatHistory

from .base import BaseManager


class ChatHistoryManager(BaseManager[ChatHistory]):
    """负责 ChatHistory 表的连接初始化与增删改查操作。"""

    model = ChatHistory
    pk_field = "id"
    editable_fields = ("name", "content")

    def add_chat_history(self, chat_history: ChatHistory) -> None:
        self._add(chat_history)

    def upsert_chat_history(self, chat_history: ChatHistory) -> None:
        self._upsert(chat_history)

    def delete_chat_history(self, id: int) -> None:
        self._delete(id)

    def edit_chat_history(self, id: int, chat_history: ChatHistory) -> None:
        self._edit(id, chat_history)

    def get_chat_history(self, id: int) -> Optional[ChatHistory]:
        return self._get(id)

    def list_chat_history(self) -> list[ChatHistory]:
        return self._list()


__all__ = ["ChatHistoryManager"]
