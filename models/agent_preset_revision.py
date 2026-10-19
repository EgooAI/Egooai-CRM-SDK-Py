from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, ForeignKey, Index, String
from sqlmodel import Field, SQLModel

from utils.common import utc_now

from .agent_preset import LLM_MAX_LEVEL


class AgentPresetRevision(SQLModel, table=True):
    """单条 AgentPreset 历史快照；``source`` 由宿主定义，SDK 不解释其取值。"""

    __tablename__ = "agent_preset_revision"
    __table_args__ = (Index("idx_agent_preset_revision_apid", "apid"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    apid: str = Field(
        sa_column=Column(
            "apid",
            String,
            ForeignKey("agentpreset.apid", ondelete="CASCADE"),
            nullable=False,
        )
    )
    name: str
    description: str
    prompt: str
    llm_level: int = Field(ge=0, le=LLM_MAX_LEVEL)
    tools: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    requires_tool: bool = Field(default=False)
    source: str = ""
    note: str = ""
    created_time: datetime = Field(default_factory=utc_now)


__all__ = ["AgentPresetRevision"]
