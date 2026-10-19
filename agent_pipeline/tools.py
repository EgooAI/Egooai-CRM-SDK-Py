from __future__ import annotations

import inspect
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from types import UnionType
from typing import Annotated, Any, Callable, Optional, Union, get_args, get_origin, get_type_hints

from agent_pipeline.resolver import AgentPresetRuntimeConfig
from agent_pipeline.types import EffectIntent, ToolCallRecord, ToolExecutionResult

CATEGORY_READ = "read"
CATEGORY_EFFECT = "effect"
DEFAULT_TOOL_TIMEOUT_SECONDS = 30.0


class ToolContext:
    """Run context injected into tools that declare a ``ctx: ToolContext`` parameter.

    The SDK treats ``scope`` as opaque; the host fills it. Effect tools append
    intents here instead of performing the action themselves.
    """

    def __init__(self, *, mode: str = "", scope: Any = None) -> None:
        self.mode = mode
        self.scope = scope
        self._intents: list[EffectIntent] = []
        # Payloads recorded by successful effect calls; duplicates are checked
        # against this even though only the latest round's intents survive.
        self.recorded: list[dict[str, Any]] = []
        self.recorded_sequence = 0

    def emit(
        self,
        kind: str,
        content: dict[str, Any],
        *,
        call_id: Optional[str] = None,
        sequence: Optional[int] = None,
    ) -> EffectIntent:
        intent = EffectIntent(
            kind=kind,
            content=dict(content),
            call_id=call_id,
            mode=self.mode,
            sequence=sequence if sequence is not None else len(self._intents) + 1,
        )
        self._intents.append(intent)
        return intent

    def next_sequence(self) -> int:
        """Run-wide ordinal for the next effect, across rounds and calls."""
        self.recorded_sequence += 1
        return self.recorded_sequence

    @property
    def intents(self) -> list[EffectIntent]:
        return list(self._intents)

    def child(self) -> "ToolContext":
        """A collector for one call, sharing mode, scope and prior recordings."""
        child = ToolContext(mode=self.mode, scope=self.scope)
        child.recorded = list(self.recorded)
        child.recorded_sequence = self.recorded_sequence
        return child


@dataclass(frozen=True)
class ToolSpec:
    """Host-provided tool metadata; ``name`` must match the registered callable."""

    name: str
    title: str = ""
    description: str = ""
    category: str = CATEGORY_READ
    repeatable: bool = True
    max_calls: Optional[int] = None
    parameter_descriptions: dict[str, str] = field(default_factory=dict)
    timeout_seconds: Optional[float] = None


def _unwrap_annotation(annotation: object) -> object:
    if annotation is inspect._empty:
        return annotation

    origin = get_origin(annotation)
    if origin is Annotated:
        return _unwrap_annotation(get_args(annotation)[0])
    if origin in (UnionType, Union):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def annotation_description(annotation: object) -> str:
    """String metadata attached through ``Annotated[T, "说明"]``."""
    if get_origin(annotation) is Annotated:
        for meta in get_args(annotation)[1:]:
            if isinstance(meta, str) and meta.strip():
                return meta.strip()
    return ""


def is_context_parameter(annotation: object) -> bool:
    return _unwrap_annotation(annotation) is ToolContext


def json_type_of(annotation: object) -> str:
    normalized = _unwrap_annotation(annotation)
    origin = get_origin(normalized)
    if origin is dict:
        return "object"
    if origin is list:
        return "array"
    if normalized in (int, float):
        return "number"
    if normalized is bool:
        return "boolean"
    if normalized is dict:
        return "object"
    if normalized is list:
        return "array"
    return "string"


def build_tool_schema(
    tool: Callable[..., Any], spec: Optional[ToolSpec] = None
) -> dict[str, Any]:
    signature = inspect.signature(tool)
    type_hints = get_type_hints(tool, include_extras=True)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in signature.parameters.values():
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            continue
        annotation = type_hints.get(parameter.name, parameter.annotation)
        if is_context_parameter(annotation):
            continue
        entry: dict[str, Any] = {"type": json_type_of(annotation)}
        described = annotation_description(annotation)
        if not described and spec is not None:
            described = spec.parameter_descriptions.get(parameter.name, "")
        if described:
            entry["description"] = described
        properties[parameter.name] = entry
        if parameter.default is inspect._empty:
            required.append(parameter.name)
    return {"type": "object", "properties": properties, "required": required}


class ToolExecutor:
    """Execute resolved tools with context injection, timeouts and results-not-exceptions."""

    def __init__(self, default_timeout_seconds: Optional[float] = DEFAULT_TOOL_TIMEOUT_SECONDS) -> None:
        self.default_timeout_seconds = default_timeout_seconds

    @classmethod
    def _coerce_value(cls, value: Any, annotation: object) -> Any:
        normalized_annotation = _unwrap_annotation(annotation)
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
        type_hints = get_type_hints(tool, include_extras=True)
        normalized: dict[str, Any] = {}
        for key, value in tool_input.items():
            parameter = signature.parameters.get(key)
            if parameter is None:
                normalized[key] = value
                continue
            normalized[key] = cls._coerce_value(value, type_hints.get(key, parameter.annotation))
        return normalized

    def _call_with_timeout(self, func, *args, timeout: Optional[float], **kwargs):
        if timeout is None:
            return func(*args, **kwargs)
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="tool-call") as pool:
            future = pool.submit(func, *args, **kwargs)
            return future.result(timeout=timeout)

    def execute(
        self,
        runtime: AgentPresetRuntimeConfig,
        tool_name: str,
        tool_input: dict | None,
        *,
        context: Optional[ToolContext] = None,
        call_id: Optional[str] = None,
        round_index: int = 0,
    ) -> tuple[ToolExecutionResult, ToolCallRecord]:
        """Run one call. Unknown names, bad arguments, exceptions and timeouts become failures."""
        started = time.perf_counter()
        arguments = dict(tool_input or {})
        if tool_name not in runtime.tool_names:
            error = (
                f"未知工具 {tool_name}：该 Agent 未挂载此工具，请改用已提供的工具或直接回答。"
            )
            result = ToolExecutionResult(name=tool_name, ok=False, error=error, call_id=call_id)
            return result, ToolCallRecord(
                call_id=call_id, name=tool_name, arguments=arguments, ok=False,
                error=error, duration_ms=(time.perf_counter() - started) * 1000, round=round_index,
            )

        tool = runtime.tools[runtime.tool_names.index(tool_name)]
        spec = next(
            (item for name, item in zip(runtime.tool_names, runtime.tool_specs, strict=False) if name == tool_name),
            None,
        )
        type_hints = get_type_hints(tool, include_extras=True)

        error: Optional[str] = None
        content: Any = None
        try:
            keyword_input = self._normalize_keyword_input(tool, arguments)
            for parameter in inspect.signature(tool).parameters.values():
                if is_context_parameter(type_hints.get(parameter.name, parameter.annotation)):
                    keyword_input[parameter.name] = context if context is not None else ToolContext()
            timeout = spec.timeout_seconds if spec is not None and spec.timeout_seconds else self.default_timeout_seconds
            content = self._call_with_timeout(tool, timeout=timeout, **keyword_input)
        except (TypeError, ValueError) as exc:
            error = f"工具 {tool_name} 参数不合法：{exc}"
        except FutureTimeoutError:
            error = f"工具 {tool_name} 执行超时。"
        except Exception as exc:
            error = f"工具 {tool_name} 执行失败：{type(exc).__name__}: {exc}"

        record = ToolCallRecord(
            call_id=call_id,
            name=tool_name,
            arguments=arguments,
            ok=error is None,
            content=content if error is None else None,
            error=error,
            duration_ms=(time.perf_counter() - started) * 1000,
            round=round_index,
        )
        return ToolExecutionResult(
            name=tool_name, ok=error is None, content=content, error=error, call_id=call_id,
        ), record


def tool_use_instruction(spec: Optional[ToolSpec], name: str) -> str:
    """One line of the generated tool-usage section for a tool."""
    title = f"{name}（{spec.title}）" if spec is not None and spec.title else name
    if spec is None:
        return f"- {title}：可以按需调用，不必重复调用。"
    if spec.category == CATEGORY_EFFECT:
        detail = spec.description or "调用即产生一条待确认的对外动作。"
        return f"- {title}：效果类工具。{detail}"
    if not spec.repeatable:
        return f"- {title}：读取类工具，每次运行最多调用一次，不必重复调用。"
    if spec.max_calls is not None:
        return f"- {title}：读取类工具，每次运行最多调用 {spec.max_calls} 次。"
    return f"- {title}：读取类工具，可以按需调用，不必重复调用。"


__all__ = [
    "CATEGORY_EFFECT",
    "CATEGORY_READ",
    "DEFAULT_TOOL_TIMEOUT_SECONDS",
    "ToolContext",
    "ToolExecutor",
    "ToolSpec",
    "annotation_description",
    "build_tool_schema",
    "is_context_parameter",
    "json_type_of",
    "tool_use_instruction",
]
