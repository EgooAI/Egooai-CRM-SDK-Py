from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core import LLMConfig, register_llm
from core.llm_api_config import LLMApiConfigManager

def _validate_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _validate_optional_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _validate_optional_positive_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _load_payload(config_path: Path | str | None = None) -> dict[str, Any]:
    if config_path is None:
        payload = LLMApiConfigManager().to_payload()
        if payload is not None:
            return payload
        raise FileNotFoundError("LLM config not found in llm_api_config table")

    resolved_path = Path(config_path).resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"LLM config file not found: {resolved_path}")

    with resolved_path.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file) or {}

    if not isinstance(payload, dict):
        raise ValueError("LLM config file must contain a mapping at the top level")
    return payload


def load_default_llm_levels(config_path: Path | str | None = None) -> dict[int, LLMConfig]:
    payload = _load_payload(config_path)

    default = payload.get("default", {})
    if default is None:
        default = {}
    if not isinstance(default, dict):
        raise ValueError("LLM config 'default' must be a mapping when provided")

    default_base_url = default.get("base_url")
    default_api_key = default.get("api_key")
    default_model_name = default.get("model_name")
    default_system_prompt = _validate_optional_str(
        default.get("system_prompt"),
        "default.system_prompt",
    )
    default_context = _validate_optional_positive_int(
        default.get("context"),
        "default.context",
    )
    default_context_limit_output_text = _validate_optional_str(
        default.get("context_limit_output_text"),
        "default.context_limit_output_text",
    )
    default_tool_round_limit_output_text = _validate_optional_str(
        default.get("tool_round_limit_output_text"),
        "default.tool_round_limit_output_text",
    )
    default_max_tool_rounds = _validate_optional_positive_int(
        default.get("max_tool_rounds"),
        "default.max_tool_rounds",
    )

    raw_levels = payload.get("levels", {level: {} for level in range(5)})
    if not isinstance(raw_levels, dict):
        raise ValueError("levels must be a mapping if provided")

    llm_levels: dict[int, LLMConfig] = {}
    if default:
        levels_to_load = list(range(5))
    else:
        levels_to_load = sorted(
            int(level_key)
            for level_key in raw_levels.keys()
            if str(level_key).isdigit() and 0 <= int(level_key) <= 4
        )

    for raw_level in levels_to_load:
        level_override = raw_levels.get(raw_level, raw_levels.get(str(raw_level), {}))
        if level_override is None:
            level_override = {}
        if not isinstance(level_override, dict):
            raise ValueError(f"levels.{raw_level} must be a mapping")

        base_url = level_override.get("base_url", default_base_url)
        api_key = level_override.get("api_key", default_api_key)
        model_name = level_override.get("model_name", default_model_name)
        system_prompt = _validate_optional_str(
            level_override.get("system_prompt", default_system_prompt),
            f"levels.{raw_level}.system_prompt",
        )
        context = _validate_optional_positive_int(
            level_override.get("context", default_context),
            f"levels.{raw_level}.context",
        )
        context_limit_output_text = _validate_optional_str(
            level_override.get("context_limit_output_text", default_context_limit_output_text),
            f"levels.{raw_level}.context_limit_output_text",
        )
        tool_round_limit_output_text = _validate_optional_str(
            level_override.get("tool_round_limit_output_text", default_tool_round_limit_output_text),
            f"levels.{raw_level}.tool_round_limit_output_text",
        )
        max_tool_rounds = _validate_optional_positive_int(
            level_override.get("max_tool_rounds", default_max_tool_rounds),
            f"levels.{raw_level}.max_tool_rounds",
        )

        llm_levels[raw_level] = LLMConfig(
            base_url=_validate_str(base_url, f"levels.{raw_level}.base_url"),
            api_key=_validate_str(api_key, f"levels.{raw_level}.api_key"),
            model_name=_validate_str(model_name, f"levels.{raw_level}.model_name"),
            system_prompt=system_prompt,
            context=context,
            context_limit_output_text=context_limit_output_text,
            tool_round_limit_output_text=tool_round_limit_output_text,
            max_tool_rounds=max_tool_rounds,
        )

    return llm_levels


def register_default_llms(config_path: Path | str | None = None) -> dict[int, LLMConfig]:
    llm_levels = load_default_llm_levels(config_path)
    for level, config in llm_levels.items():
        register_llm(level, config)
    return llm_levels


__all__ = [
    "load_default_llm_levels",
    "register_default_llms",
]
