from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core import LLMConfig, register_llm

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "llm_api.yaml"
DEFAULT_EXAMPLE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "llm_api.example.yaml"


def _validate_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def load_default_llm_levels(config_path: Path | str | None = None) -> dict[int, LLMConfig]:
    resolved_path = Path(config_path or DEFAULT_CONFIG_PATH).resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"LLM config file not found: {resolved_path}")

    with resolved_path.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file) or {}

    if not isinstance(payload, dict):
        raise ValueError("llm_api.yaml must contain a mapping at the top level")

    default = payload.get("default")
    if not isinstance(default, dict):
        raise ValueError("llm_api.yaml must contain a 'default' mapping")

    default_base_url = _validate_str(default.get("base_url"), "default.base_url")
    default_api_key = _validate_str(default.get("api_key"), "default.api_key")
    default_model_name = _validate_str(default.get("model_name"), "default.model_name")

    raw_levels = payload.get("levels", {level: {} for level in range(5)})
    if not isinstance(raw_levels, dict):
        raise ValueError("levels must be a mapping if provided")

    llm_levels: dict[int, LLMConfig] = {}
    for raw_level in range(5):
        level_override = raw_levels.get(raw_level, raw_levels.get(str(raw_level), {}))
        if level_override is None:
            level_override = {}
        if not isinstance(level_override, dict):
            raise ValueError(f"levels.{raw_level} must be a mapping")

        base_url = level_override.get("base_url", default_base_url)
        api_key = level_override.get("api_key", default_api_key)
        model_name = level_override.get("model_name", default_model_name)

        llm_levels[raw_level] = LLMConfig(
            base_url=_validate_str(base_url, f"levels.{raw_level}.base_url"),
            api_key=_validate_str(api_key, f"levels.{raw_level}.api_key"),
            model_name=_validate_str(model_name, f"levels.{raw_level}.model_name"),
        )

    return llm_levels


def register_default_llms(config_path: Path | str | None = None) -> dict[int, LLMConfig]:
    llm_levels = load_default_llm_levels(config_path)
    for level, config in llm_levels.items():
        register_llm(level, config)
    return llm_levels


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_EXAMPLE_CONFIG_PATH",
    "load_default_llm_levels",
    "register_default_llms",
]
