from typing import Any, Optional

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel


class ChatHistory(SQLModel, table=True):
    __tablename__ = "chat_history"
    __table_args__ = (Index("idx_chat_history_experiment", "experiment_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    content: Any = Field(sa_column=Column(JSON, nullable=False))
    # Set when this session is one variant of an experiment; NULL for standalone
    # sessions. No foreign key: deleting an experiment merely detaches it.
    experiment_id: Optional[int] = Field(default=None)


__all__ = ["ChatHistory"]
