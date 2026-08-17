from pathlib import Path
from typing import Optional

from sqlalchemy import inspect
from sqlmodel import Session, select

from models.chat_history import ChatHistory
from utils.common import bootstrap_engine, get_database_lock


class ChatHistoryManager:
    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        self.database_path, self.engine = bootstrap_engine(database_path)
        self._lock = get_database_lock(self.database_path)

    @staticmethod
    def _payload_tuple(chat_history: ChatHistory) -> tuple[object, ...]:
        return (
            chat_history.name,
            chat_history.content,
        )

    @staticmethod
    def _apply_chat_history_updates(current_chat_history: ChatHistory, chat_history: ChatHistory) -> None:
        current_chat_history.name = chat_history.name
        current_chat_history.content = chat_history.content

    def add_chat_history(self, chat_history: ChatHistory) -> None:
        with self._lock:
            with Session(self.engine) as session:
                session.add(chat_history)
                session.commit()
                session.refresh(chat_history)

    def upsert_chat_history(self, chat_history: ChatHistory) -> None:
        with self._lock:
            with Session(self.engine) as session:
                if chat_history.id is None:
                    session.add(chat_history)
                    session.commit()
                    session.refresh(chat_history)
                    return

                current_chat_history = session.get(ChatHistory, chat_history.id)
                if current_chat_history is None:
                    raise ValueError(f"ChatHistory {chat_history.id} not found")

                if self._payload_tuple(current_chat_history) == self._payload_tuple(chat_history):
                    return

                self._apply_chat_history_updates(current_chat_history, chat_history)
                session.add(current_chat_history)
                session.commit()
                session.refresh(current_chat_history)

    def delete_chat_history(self, id: int) -> None:
        with self._lock:
            with Session(self.engine) as session:
                current_chat_history = session.get(ChatHistory, id)
                if current_chat_history is None:
                    return

                session.delete(current_chat_history)
                session.commit()

    def edit_chat_history(self, id: int, chat_history: ChatHistory) -> None:
        with self._lock:
            with Session(self.engine) as session:
                current_chat_history = session.get(ChatHistory, id)
                if current_chat_history is None:
                    raise ValueError(f"ChatHistory {id} not found")

                self._apply_chat_history_updates(current_chat_history, chat_history)

                session.add(current_chat_history)
                session.commit()
                session.refresh(current_chat_history)

    def get_chat_history(self, id: int) -> Optional[ChatHistory]:
        with Session(self.engine) as session:
            return session.get(ChatHistory, id)

    def list_chat_history(self) -> list[ChatHistory]:
        with Session(self.engine) as session:
            id_column = inspect(ChatHistory).columns.id
            statement = select(ChatHistory).order_by(id_column)
            return list(session.exec(statement).all())


__all__ = ["ChatHistoryManager"]