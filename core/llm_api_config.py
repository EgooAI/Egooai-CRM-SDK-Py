from pathlib import Path
from typing import Any
from typing import Optional

from sqlmodel import Session, select

from models.llm_api_config import LLMApiConfig
from utils.common import bootstrap_engine, get_database_lock


class LLMApiConfigManager:
    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        self.database_path, self.engine = bootstrap_engine(database_path)
        self._lock = get_database_lock(self.database_path)

    def get_config(self, level: int) -> Optional[LLMApiConfig]:
        with self._lock:
            with Session(self.engine) as session:
                return session.get(LLMApiConfig, level)

    def list_configs(self) -> list[LLMApiConfig]:
        with self._lock:
            with Session(self.engine) as session:
                statement = select(LLMApiConfig).order_by(LLMApiConfig.level)
                return list(session.exec(statement).all())

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
        with self._lock:
            with Session(self.engine) as session:
                current = session.get(LLMApiConfig, config.level)
                if current is None:
                    session.add(config)
                    session.commit()
                    session.refresh(config)
                    return

                current.base_url = config.base_url
                current.api_key = config.api_key
                current.model_name = config.model_name
                current.system_prompt = config.system_prompt
                current.context = config.context
                current.max_tool_rounds = config.max_tool_rounds
                session.add(current)
                session.commit()
                session.refresh(current)
                self._sync_config(config, current)

    def replace_configs(self, configs: list[LLMApiConfig]) -> None:
        with self._lock:
            with Session(self.engine) as session:
                for current in session.exec(select(LLMApiConfig)).all():
                    session.delete(current)
                for config in configs:
                    session.add(config)
                session.commit()

    @staticmethod
    def _sync_config(target: LLMApiConfig, source: LLMApiConfig) -> None:
        target.level = source.level
        target.base_url = source.base_url
        target.api_key = source.api_key
        target.model_name = source.model_name
        target.system_prompt = source.system_prompt
        target.context = source.context
        target.max_tool_rounds = source.max_tool_rounds


__all__ = ["LLMApiConfigManager"]
