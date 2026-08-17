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


@dataclass(frozen=True)
class LLMToolCall:
    name: str
    tool_input: dict[str, Any] = field(default_factory=dict)
    call_id: Optional[str] = None


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


@dataclass(frozen=True)
class LLMResponse:
    text: str
    needs_tool: bool = False
    tool_call: Optional[LLMToolCall] = None
    raw: Any = None


@dataclass(frozen=True)
class ToolExecutionResult:
    name: str
    ok: bool
    content: Any = None
    error: Optional[str] = None


@dataclass(frozen=True)
class AgentPipelineResult:
    status: AgentPipelineResultStatus
    runtime: AgentPresetRuntimeConfig
    output_text: str
    iterations: int
    tool_call: Optional[LLMToolCall] = None
    tool_result: Optional[ToolExecutionResult] = None
    raw_responses: list[Any] = field(default_factory=list)