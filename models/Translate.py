from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Translate(SQLModel, table=True):
    tid: Optional[int] = Field(default=None, primary_key=True)
    content: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))


__all__ = ["Translate"]
