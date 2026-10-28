from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel

from utils.common import utc_now


class Experiment(SQLModel, table=True):
    """A tuning experiment: one frozen starting point compared across variants.

    The SDK owns only the experiment's identity and an opaque JSON ``content``
    document. Host applications keep the frozen input, the scripted steps and
    the annotations there; the SDK never interprets them. Variants are ordinary
    ``ChatHistory`` rows that point back through ``experiment_id``.
    """

    __tablename__ = "agent_experiment"
    __table_args__ = (Index("idx_agent_experiment_agent", "agent_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str
    name: str = ""
    content: Any = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_time: datetime = Field(default_factory=utc_now)
    updated_time: datetime = Field(default_factory=utc_now)


__all__ = ["Experiment"]
