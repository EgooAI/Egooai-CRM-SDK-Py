from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from .Customer import utc_now
from .SessionChat import generate_session_chatid


class SessionMeta(SQLModel, table=True):
    sid: Optional[int] = Field(default=None, primary_key=True)
    name: str
    chatid: str = Field(default_factory=generate_session_chatid, index=True, unique=True)
    participants: Optional[list[int]] = Field(default=None, sa_column=Column(JSON))
    created_time: datetime = Field(default_factory=utc_now)
    updated_time: datetime = Field(
        default_factory=utc_now,
        sa_column_kwargs={"onupdate": utc_now},
    )


__all__ = ["SessionMeta"]
