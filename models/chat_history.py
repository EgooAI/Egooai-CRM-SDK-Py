from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class ChatHistory(SQLModel, table=True):
    __tablename__ = "chat_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    content: Any = Field(sa_column=Column(JSON, nullable=False))


__all__ = ["ChatHistory"]