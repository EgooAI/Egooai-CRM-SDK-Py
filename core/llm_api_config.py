from pathlib import Path
from typing import Any, Optional

from sqlmodel import Session, select

from models.llm_api_config import LLMApiConfig

from .base import BaseManager


class LLMApiConfigManager(BaseManager[LLMApiConfig]):
    """负责 llm_api_config 表的连接初始化与增删改查操作。"""

    model = LLMApiConfig
    pk_field = "level"
    editable_fields = ("base_url", "api_key", "model_name", "system_prompt", "context", "max_tool_rounds")
    pk_is_auto = False

    def get_config(self, level: int) -> Optional[LLMApiConfig]:
        return self._get(level)

    def list_configs(self) -> list[LLMApiConfig]:
        return self._list()

    def to_payload(self) -> dict[str, Any] | None:
        configs = self.list_configs()
        if not configs:
            return None
        return {
            "levels": {
                config.level: {
                    "base_url": config.base_url,
                    "api_key": config.api_key,
                    "model_name": config.model_name,
                    "system_prompt": config.system_prompt,
                    "context": config.context,
                    "max_tool_rounds": config.max_tool_rounds,
                }
                for config in configs
            }
        }

    def upsert_config(self, config: LLMApiConfig) -> None:
        self._upsert(config)

    def replace_configs(self, configs: list[LLMApiConfig]) -> None:
        with self._lock:
            with Session(self.engine) as session:
                for current in session.exec(select(LLMApiConfig)).all():
                    session.delete(current)
                for config in configs:
                    session.add(config)
                session.commit()


__all__ = ["LLMApiConfigManager"]
