from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from utils.common import utc_now


class Account(SQLModel, table=True):
    aid: Optional[int] = Field(default=None, primary_key=True)
    cid: int = Field(foreign_key="customer.cid")
    pid: Optional[str] = Field(default=None, foreign_key="platform.pid")
    account: Optional[str] = Field(default=None)
    nickname: Optional[str] = Field(default=None)
    avatar: Optional[str] = Field(default=None)
    sids: Optional[list[int]] = Field(default=None, sa_column=Column(JSON))
    extra: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_time: datetime = Field(default_factory=utc_now)
    updated_time: datetime = Field(
        default_factory=utc_now,
        sa_column_kwargs={"onupdate": utc_now},
    )


__all__ = ["Account"]
