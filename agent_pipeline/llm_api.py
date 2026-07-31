from __future__ import annotations

import os
from pathlib import Path

from core import LLMConfig, register_llm
from core.llm_api_config import LLMApiConfigManager

_CONTEXT_LIMIT_OUTPUT_ENV = "LLM_CONTEXT_LIMIT_OUTPUT_TEXT"
_TOOL_ROUND_LIMIT_OUTPUT_ENV = "LLM_TOOL_ROUND_LIMIT_OUTPUT_TEXT"
_DEFAULT_CONTEXT_LIMIT_OUTPUT_TEXT = "上下文超过限制"
_DEFAULT_TOOL_ROUND_LIMIT_OUTPUT_TEXT = "调用超过次数限制"


def _none_if_empty(value: str | None) -> str | None:
    return value or None


def _env_text(key: str, default: str) -> str:
    return os.getenv(key) or default


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
            context_limit_output_text=_env_text(_CONTEXT_LIMIT_OUTPUT_ENV, _DEFAULT_CONTEXT_LIMIT_OUTPUT_TEXT),
            tool_round_limit_output_text=_env_text(
                _TOOL_ROUND_LIMIT_OUTPUT_ENV,
                _DEFAULT_TOOL_ROUND_LIMIT_OUTPUT_TEXT,
            ),
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
