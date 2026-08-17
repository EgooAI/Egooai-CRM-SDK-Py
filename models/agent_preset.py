from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

LLM_MAX_LEVEL = 4


class AgentPreset(SQLModel, table=True):
    apid: str = Field(primary_key=True)
    name: str
    description: str
    prompt: str
    llm_level: int = Field(ge=0, le=LLM_MAX_LEVEL)
    tools: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))


__all__ = ["AgentPreset", "LLM_MAX_LEVEL"]
