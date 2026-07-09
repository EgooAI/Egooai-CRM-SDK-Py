from pathlib import Path
from typing import Optional

from sqlalchemy import inspect
from sqlmodel import Session, select

from models.message import Message
from utils.common import bootstrap_engine, get_database_lock


class MessageManager:
    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        self.database_path, self.engine = bootstrap_engine(database_path)
        self._lock = get_database_lock(self.database_path)

    @staticmethod
    def _payload_tuple(message: Message) -> tuple[object, ...]:
        return (
            message.sid,
            message.sender,
            message.read,
            message.content,
            message.type,
        )

    @staticmethod
    def _apply_message_updates(current_message: Message, message: Message) -> None:
        current_message.sid = message.sid
        current_message.sender = message.sender
        current_message.read = message.read
        current_message.content = message.content
        current_message.type = message.type

    def add_message(self, message: Message) -> None:
        with self._lock:
            with Session(self.engine) as session:
                session.add(message)
                session.commit()
                session.refresh(message)

    def upsert_message(self, message: Message) -> None:
        with self._lock:
            with Session(self.engine) as session:
                current_message = session.get(Message, message.extrenal_mid)
                if current_message is None:
                    session.add(message)
                    session.commit()
                    session.refresh(message)
                    return

                if self._payload_tuple(current_message) == self._payload_tuple(message):
                    return

                self._apply_message_updates(current_message, message)
                session.add(current_message)
                session.commit()
                session.refresh(current_message)

    def delete_message(self, extrenal_mid: str) -> None:
        with self._lock:
            with Session(self.engine) as session:
                current_message = session.get(Message, extrenal_mid)
                if current_message is None:
                    return

                session.delete(current_message)
                session.commit()

    def edit_message(self, extrenal_mid: str, message: Message) -> None:
        with self._lock:
            with Session(self.engine) as session:
                current_message = session.get(Message, extrenal_mid)
                if current_message is None:
                    raise ValueError(f"Message {extrenal_mid} not found")

                self._apply_message_updates(current_message, message)

                session.add(current_message)
                session.commit()
                session.refresh(current_message)

    def get_message(self, extrenal_mid: str) -> Optional[Message]:
        with Session(self.engine) as session:
            return session.get(Message, extrenal_mid)

    def list_message(self) -> list[Message]:
        with Session(self.engine) as session:
            extrenal_mid_column = inspect(Message).columns.extrenal_mid
            statement = select(Message).order_by(extrenal_mid_column)
            return list(session.exec(statement).all())


__all__ = ["MessageManager"]
