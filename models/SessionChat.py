import re
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Table
from sqlmodel import Field, SQLModel

from .Customer import utc_now

_SESSION_CHAT_TABLE_PREFIX = "sessionchat_"
_SESSION_CHATID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class SessionChat(SQLModel):
    id: Optional[int] = Field(default=None)
    sender: int
    type: str
    content: Any
    read: Optional[bool] = Field(default=None)
    created_time: datetime = Field(default_factory=utc_now)
    updated_time: datetime = Field(default_factory=utc_now)


def generate_session_chatid() -> str:
    return uuid.uuid4().hex


def normalize_session_chatid(chatid: str) -> str:
    if not _SESSION_CHATID_PATTERN.fullmatch(chatid):
        raise ValueError("chatid must be a 32-character lowercase hexadecimal string")
    return chatid


def resolve_session_chat_table_name(chatid: str) -> str:
    normalized_chatid = normalize_session_chatid(chatid)
    return f"{_SESSION_CHAT_TABLE_PREFIX}{normalized_chatid}"


def get_session_chat_table(chatid: str) -> Table:
    physical_table_name = resolve_session_chat_table_name(chatid)
    existing_table = SQLModel.metadata.tables.get(physical_table_name)
    if existing_table is not None:
        return existing_table

    return Table(
        physical_table_name,
        SQLModel.metadata,
        Column("id", Integer, primary_key=True),
        Column("sender", Integer, nullable=False),
        Column("type", String, nullable=False),
        Column("content", JSON, nullable=False),
        Column("read", Boolean, nullable=True),
        Column("created_time", DateTime(timezone=True), nullable=False),
        Column("updated_time", DateTime(timezone=True), nullable=False),
    )


__all__ = [
    "SessionChat",
    "generate_session_chatid",
    "normalize_session_chatid",
    "resolve_session_chat_table_name",
    "get_session_chat_table",
]
