from sqlmodel import Field, SQLModel


class LLMApiConfig(SQLModel, table=True):
    __tablename__ = "llm_api_config"

    level: int = Field(primary_key=True, ge=0, le=4)
    base_url: str
    api_key: str
    model_name: str
    system_prompt: str = ""
    context: int = Field(default=12000, gt=0)
    max_tool_rounds: int | None = Field(default=None, gt=0)


__all__ = ["LLMApiConfig"]
