from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class AccountMapping(SQLModel, table=True):
    __table_args__ = (Index("idx_account_mapping_type_key", "type", "key"),)

    amid: Optional[int] = Field(default=None, primary_key=True)
    aid: int = Field(foreign_key="account.aid")
    type: Optional[str] = Field(default=None)
    key: Optional[str] = Field(default=None)


__all__ = ["AccountMapping"]
