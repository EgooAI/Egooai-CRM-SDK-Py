from __future__ import annotations

from pathlib import Path

from core import LLMConfig, register_llm
from core.llm_api_config import LLMApiConfigManager


def _none_if_empty(value: str | None) -> str | None:
    return value or None


def load_default_llm_levels(database_path: Path | str | None = None) -> dict[int, LLMConfig]:
    manager = LLMApiConfigManager(database_path)
    try:
        configs = manager.list_configs()
    finally:
        manager.engine.dispose()

    if not configs:
        raise ValueError("LLM config not found in llm_api_config table")

    return {
        config.level: LLMConfig(
            base_url=config.base_url,
            api_key=config.api_key,
            model_name=config.model_name,
            system_prompt=_none_if_empty(config.system_prompt),
            context=config.context,
            context_limit_output_text=_none_if_empty(config.context_limit_output_text),
            tool_round_limit_output_text=_none_if_empty(config.tool_round_limit_output_text),
            max_tool_rounds=config.max_tool_rounds,
        )
        for config in configs
    }


def register_default_llms(database_path: Path | str | None = None) -> dict[int, LLMConfig]:
    llm_levels = load_default_llm_levels(database_path)
    for level, config in llm_levels.items():
        register_llm(level, config)
    return llm_levels


__all__ = [
    "load_default_llm_levels",
    "register_default_llms",
]
