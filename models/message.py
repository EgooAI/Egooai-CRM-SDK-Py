from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Message(SQLModel, table=True):
    external_mid: str = Field(primary_key=True)
    sid: int = Field(foreign_key="sessionmeta.sid", index=True)
    sender: int = Field(foreign_key="account.aid", index=True)
    read: Optional[bool] = Field(default=None)
    content: Any = Field(sa_column=Column(JSON, nullable=False))
    type: str
    created_at: Optional[datetime] = Field(default=None)


__all__ = ["Message"]
