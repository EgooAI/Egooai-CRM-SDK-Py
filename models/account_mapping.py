from typing import Optional

from sqlmodel import Field, SQLModel


class AccountMapping(SQLModel, table=True):
    amid: Optional[int] = Field(default=None, primary_key=True)
    aid: int = Field(foreign_key="account.aid")
    type: Optional[str] = Field(default=None)
    key: Optional[str] = Field(default=None)


__all__ = ["AccountMapping"]
