"""Describes immutable, content-addressed binary resources."""

from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class Resource(SQLModel, table=True):
    resource_id: str = Field(primary_key=True)
    file_md5: str = Field(index=True)
    size: int
    media_type: str
    attributes: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    state: str = "ready"
    created_at: float
    retain_until: float


__all__ = ["Resource"]
