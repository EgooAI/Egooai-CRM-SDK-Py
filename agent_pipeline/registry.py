from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Any, Optional

from models.agent_preset import LLM_MAX_LEVEL


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model_name: str
    system_prompt: Optional[str] = None
    context: Optional[int] = None
    max_tool_rounds: Optional[int] = None


class ToolRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._tools: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, func: Callable[..., Any]) -> None:
        if not name:
            raise ValueError("tool name must not be empty")
        if not callable(func):
            raise TypeError("tool func must be callable")
        with self._lock:
            self._tools[name] = func

    def get(self, name: str) -> Optional[Callable[..., Any]]:
        with self._lock:
            return self._tools.get(name)

    def require(self, name: str) -> Callable[..., Any]:
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"Tool {name} is not registered")
        return tool

    def list(self) -> dict[str, Callable[..., Any]]:
        with self._lock:
            return dict(self._tools)

    def clear(self) -> None:
        with self._lock:
            self._tools.clear()


class LLMRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._configs: dict[int, LLMConfig] = {}

    @staticmethod
    def _validate_level(level: int) -> None:
        if not 0 <= level <= LLM_MAX_LEVEL:
            raise ValueError(f"LLM level must be between 0 and {LLM_MAX_LEVEL}")

    def register(self, level: int, config: LLMConfig) -> None:
        self._validate_level(level)
        if not isinstance(config, LLMConfig):
            raise TypeError("LLM config must be an LLMConfig instance")
        with self._lock:
            self._configs[level] = config

    def get(self, level: int) -> Optional[LLMConfig]:
        self._validate_level(level)
        with self._lock:
            return self._configs.get(level)

    def require(self, level: int) -> LLMConfig:
        config = self.get(level)
        if config is None:
            raise KeyError(f"LLM level {level} is not registered")
        return config

    def list(self) -> dict[int, LLMConfig]:
        with self._lock:
            return dict(self._configs)

    def clear(self) -> None:
        with self._lock:
            self._configs.clear()


class OutputNormalizerRegistry:
    """Register output normalizers keyed by agent preset apid.

    The pipeline applies a registered normalizer to the final response text,
    so integrations can enforce structured output without touching the SDK.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._normalizers: dict[str, Callable[[str], str]] = {}

    def register(self, apid: str, func: Callable[[str], str]) -> None:
        if not apid:
            raise ValueError("apid must not be empty")
        if not callable(func):
            raise TypeError("normalizer func must be callable")
        with self._lock:
            self._normalizers[apid] = func

    def get(self, apid: str) -> Optional[Callable[[str], str]]:
        with self._lock:
            return self._normalizers.get(apid)

    def list(self) -> dict[str, Callable[[str], str]]:
        with self._lock:
            return dict(self._normalizers)

    def clear(self) -> None:
        with self._lock:
            self._normalizers.clear()


tool_registry = ToolRegistry()
llm_registry = LLMRegistry()
output_normalizer_registry = OutputNormalizerRegistry()


def register_tool(name: str, func: Callable[..., Any]) -> None:
    tool_registry.register(name, func)


def register_llm(level: int, config: LLMConfig) -> None:
    llm_registry.register(level, config)


def register_output_normalizer(apid: str, func: Callable[[str], str]) -> None:
    output_normalizer_registry.register(apid, func)


def get_output_normalizer(apid: str) -> Optional[Callable[[str], str]]:
    return output_normalizer_registry.get(apid)


__all__ = [
    "LLMConfig",
    "ToolRegistry",
    "LLMRegistry",
    "OutputNormalizerRegistry",
    "tool_registry",
    "llm_registry",
    "output_normalizer_registry",
    "register_tool",
    "register_llm",
    "register_output_normalizer",
    "get_output_normalizer",
]