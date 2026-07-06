from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from .customer import utc_now


class Platform(SQLModel, table=True):
    pid: str = Field(primary_key=True)
    name: str
    extra: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_time: datetime = Field(default_factory=utc_now)
    updated_time: datetime = Field(
        default_factory=utc_now,
        sa_column_kwargs={"onupdate": utc_now},
    )


__all__ = ["Platform"]
