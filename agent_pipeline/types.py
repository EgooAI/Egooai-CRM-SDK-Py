from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from agent_pipeline.resolver import AgentPresetRuntimeConfig
from models.agent_preset import AgentPreset


class AgentPipelineResultStatus(str, Enum):
    COMPLETED = "completed"
    CONTEXT_LIMITED = "context_limited"
    TOOL_ROUNDS_LIMITED = "tool_rounds_limited"


@dataclass(frozen=True)
class AgentPipelineInput:
    user_input: str
    apid: Optional[str] = None
    agent_preset: Optional[AgentPreset] = None
    # Host-provided run context. The SDK never interprets its contents; tools that
    # declare a ``ToolContext`` parameter receive it at execution time.
    tool_context: Any = None
    # ``auto`` (default), ``required`` or ``none``; ``none`` never advertises tools.
    tool_choice: str = "auto"


@dataclass(frozen=True)
class LLMToolCall:
    name: str
    tool_input: dict[str, Any] = field(default_factory=dict)
    call_id: Optional[str] = None
    # Set when the provider returned unparsable arguments JSON; the executor
    # turns it into a failure result instead of aborting the run.
    input_error: Optional[str] = None


@dataclass(frozen=True)
class LLMToolSchema:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMRequest:
    system_prompt: str
    user_input: str
    tool_prompt: str
    tool_schemas: list[LLMToolSchema] = field(default_factory=list)
    tool_results: list["ToolExecutionResult"] = field(default_factory=list)
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    # Ordered exchanges: one entry per assistant turn, each with the calls that
    # turn requested and their matching results. Callers that only fill the flat
    # ``tool_calls``/``tool_results`` lists still work; the LLM client falls back
    # to the flat pairing when this is empty.
    tool_exchanges: list["ToolExchange"] = field(default_factory=list)
    tool_choice: str = "auto"


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    def merged(self, other: "LLMUsage") -> "LLMUsage":
        return LLMUsage(
            prompt_tokens=_add(self.prompt_tokens, other.prompt_tokens),
            completion_tokens=_add(self.completion_tokens, other.completion_tokens),
            total_tokens=_add(self.total_tokens, other.total_tokens),
        )


def _add(left: Optional[int], right: Optional[int]) -> Optional[int]:
    if left is None:
        return right
    if right is None:
        return left
    return left + right


@dataclass(frozen=True)
class LLMResponse:
    text: str
    needs_tool: bool = False
    tool_call: Optional[LLMToolCall] = None
    raw: Any = None
    # Every tool call in the response; ``tool_call`` remains the first one.
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)

    @property
    def calls(self) -> list[LLMToolCall]:
        if self.tool_calls:
            return list(self.tool_calls)
        return [self.tool_call] if self.tool_call is not None else []


@dataclass(frozen=True)
class ToolExecutionResult:
    name: str
    ok: bool
    content: Any = None
    error: Optional[str] = None
    call_id: Optional[str] = None
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolExchange:
    """One assistant turn that requested tools and the results that answered it."""

    calls: list[LLMToolCall] = field(default_factory=list)
    results: list[ToolExecutionResult] = field(default_factory=list)


@dataclass(frozen=True)
class ToolCallRecord:
    """One executed tool call as reported to the caller."""

    call_id: Optional[str]
    name: str
    arguments: dict[str, Any]
    ok: bool
    content: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    round: int = 0


@dataclass(frozen=True)
class EffectIntent:
    """An effect requested by a tool. The SDK only carries it; the host interprets it."""

    kind: str
    content: dict[str, Any] = field(default_factory=dict)
    call_id: Optional[str] = None
    mode: str = ""
    sequence: int = 0


@dataclass(frozen=True)
class AgentPipelineResult:
    status: AgentPipelineResultStatus
    runtime: AgentPresetRuntimeConfig
    output_text: str
    iterations: int
    tool_call: Optional[LLMToolCall] = None
    tool_result: Optional[ToolExecutionResult] = None
    raw_responses: list[Any] = field(default_factory=list)
    tool_call_records: list[ToolCallRecord] = field(default_factory=list)
    tool_exchanges: list[ToolExchange] = field(default_factory=list)
    intents: list[EffectIntent] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    duration_ms: float = 0.0

    @property
    def restricted(self) -> bool:
        return self.status is AgentPipelineResultStatus.TOOL_ROUNDS_LIMITED


__all__ = [
    "AgentPipelineInput",
    "AgentPipelineResult",
    "AgentPipelineResultStatus",
    "EffectIntent",
    "LLMRequest",
    "LLMResponse",
    "LLMToolCall",
    "LLMToolSchema",
    "LLMUsage",
    "ToolCallRecord",
    "ToolExchange",
    "ToolExecutionResult",
]
