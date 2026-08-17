from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class SessionMeta(SQLModel, table=True):
    sid: Optional[int] = Field(default=None, primary_key=True)
    key: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    participants: list[int] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))


__all__ = ["SessionMeta"]
