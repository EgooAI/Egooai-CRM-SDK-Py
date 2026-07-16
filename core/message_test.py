from pathlib import Path
from typing import Optional

from sqlalchemy import inspect
from sqlmodel import Session, select

from models.message_test import MessageTest
from utils.common import bootstrap_engine, get_database_lock


class MessageTestManager:
    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        self.database_path, self.engine = bootstrap_engine(database_path)
        self._lock = get_database_lock(self.database_path)

    @staticmethod
    def _payload_tuple(message_test: MessageTest) -> tuple[object, ...]:
        return (
            message_test.name,
            message_test.content,
        )

    @staticmethod
    def _apply_message_test_updates(current_message_test: MessageTest, message_test: MessageTest) -> None:
        current_message_test.name = message_test.name
        current_message_test.content = message_test.content

    def add_message_test(self, message_test: MessageTest) -> None:
        with self._lock:
            with Session(self.engine) as session:
                session.add(message_test)
                session.commit()
                session.refresh(message_test)

    def upsert_message_test(self, message_test: MessageTest) -> None:
        with self._lock:
            with Session(self.engine) as session:
                if message_test.id is None:
                    session.add(message_test)
                    session.commit()
                    session.refresh(message_test)
                    return

                current_message_test = session.get(MessageTest, message_test.id)
                if current_message_test is None:
                    raise ValueError(f"MessageTest {message_test.id} not found")

                if self._payload_tuple(current_message_test) == self._payload_tuple(message_test):
                    return

                self._apply_message_test_updates(current_message_test, message_test)
                session.add(current_message_test)
                session.commit()
                session.refresh(current_message_test)

    def delete_message_test(self, id: int) -> None:
        with self._lock:
            with Session(self.engine) as session:
                current_message_test = session.get(MessageTest, id)
                if current_message_test is None:
                    return

                session.delete(current_message_test)
                session.commit()

    def edit_message_test(self, id: int, message_test: MessageTest) -> None:
        with self._lock:
            with Session(self.engine) as session:
                current_message_test = session.get(MessageTest, id)
                if current_message_test is None:
                    raise ValueError(f"MessageTest {id} not found")

                self._apply_message_test_updates(current_message_test, message_test)

                session.add(current_message_test)
                session.commit()
                session.refresh(current_message_test)

    def get_message_test(self, id: int) -> Optional[MessageTest]:
        with Session(self.engine) as session:
            return session.get(MessageTest, id)

    def list_message_test(self) -> list[MessageTest]:
        with Session(self.engine) as session:
            id_column = inspect(MessageTest).columns.id
            statement = select(MessageTest).order_by(id_column)
            return list(session.exec(statement).all())


__all__ = ["MessageTestManager"]
