from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Message(SQLModel, table=True):
    extrenal_mid: str = Field(primary_key=True)
    sid: int = Field(foreign_key="sessionmeta.sid")
    sender: int = Field(foreign_key="account.aid")
    read: Optional[bool] = Field(default=None)
    content: Any = Field(sa_column=Column(JSON, nullable=False))
    type: str


__all__ = ["Message"]
