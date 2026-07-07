from datetime import date, datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from utils.common import utc_now


class Customer(SQLModel, table=True):
    cid: Optional[int] = Field(default=None, primary_key=True)
    name: Optional[str] = Field(default=None)
    sex: Optional[str] = Field(default=None)
    birthdate: Optional[date] = Field(default=None)
    region: Optional[str] = Field(default=None)
    extra: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    image: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_time: datetime = Field(default_factory=utc_now)
    updated_time: datetime = Field(
        default_factory=utc_now,
        sa_column_kwargs={"onupdate": utc_now},
    )


__all__ = ["Customer", "utc_now"]

