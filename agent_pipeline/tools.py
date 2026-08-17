from __future__ import annotations

import inspect
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from agent_pipeline.errors import ToolSelectionError
from agent_pipeline.resolver import AgentPresetRuntimeConfig
from agent_pipeline.types import ToolExecutionResult


class ToolExecutor:
    """Execute a resolved tool with light annotation-based input normalization."""

    @staticmethod
    def _unwrap_annotation(annotation: object) -> object:
        if annotation is inspect._empty:
            return annotation

        origin = get_origin(annotation)
        if origin in (UnionType, Union):
            args = [arg for arg in get_args(annotation) if arg is not type(None)]
            if len(args) == 1:
                return args[0]
        return annotation

    @classmethod
    def _coerce_value(cls, value: Any, annotation: object) -> Any:
        normalized_annotation = cls._unwrap_annotation(annotation)
        if normalized_annotation is inspect._empty or value is None:
            return value
        if normalized_annotation is float and isinstance(value, str):
            return float(value)
        if normalized_annotation is int and isinstance(value, str):
            return int(value)
        if normalized_annotation is bool and isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "y", "on"}:
                return True
            if lowered in {"false", "0", "no", "n", "off"}:
                return False
        if normalized_annotation is str and not isinstance(value, str):
            return str(value)
        return value

    @classmethod
    def _normalize_keyword_input(cls, tool, tool_input: dict[str, Any]) -> dict[str, Any]:
        signature = inspect.signature(tool)
        type_hints = get_type_hints(tool)
        normalized: dict[str, Any] = {}
        for key, value in tool_input.items():
            parameter = signature.parameters.get(key)
            if parameter is None:
                normalized[key] = value
                continue
            normalized[key] = cls._coerce_value(value, type_hints.get(key, parameter.annotation))
        return normalized

    def execute(self, runtime: AgentPresetRuntimeConfig, tool_name: str, tool_input: dict | None) -> ToolExecutionResult:
        try:
            tool_index = runtime.tool_names.index(tool_name)
        except ValueError as exc:
            raise ToolSelectionError(f"Tool {tool_name} is not available for AgentPreset {runtime.preset.apid}") from exc

        tool = runtime.tools[tool_index]
        normalized_input = tool_input or {}

        try:
            content = tool(**self._normalize_keyword_input(tool, normalized_input))
        except Exception as exc:
            return ToolExecutionResult(name=tool_name, ok=False, error=str(exc))

        return ToolExecutionResult(name=tool_name, ok=True, content=content)
