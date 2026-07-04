from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Customer(SQLModel, table=True):
    cid: Optional[int] = Field(default=None, primary_key=True)
    name: str
    sex: str
    birthdate: date
    region: str
    extra: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    image: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_time: datetime = Field(default_factory=utc_now)
    updated_time: datetime = Field(
        default_factory=utc_now,
        sa_column_kwargs={"onupdate": utc_now},
    )


__all__ = ["Customer", "utc_now"]

