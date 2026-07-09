from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class AgentPreset(SQLModel, table=True):
    apid: str = Field(primary_key=True)
    name: str
    description: str
    prompt: str
    intelevel: int = Field(ge=0, le=4)
    tools: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))


__all__ = ["AgentPreset"]
