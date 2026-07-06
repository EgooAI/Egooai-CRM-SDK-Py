from typing import Optional

from sqlmodel import Field, SQLModel


class Version(SQLModel, table=True):
    key: Optional[str] = Field(default="version", primary_key=True)
    value: str = Field(default="1.0.0")


__all__ = ["Version"]
