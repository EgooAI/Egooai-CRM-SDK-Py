from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

from agent_pipeline.registry import (
    LLMConfig,
    llm_registry,
    output_normalizer_registry,
    tool_registry,
)
from core.agent_preset import AgentPresetManager
from models.agent_preset import AgentPreset


@dataclass(frozen=True)
class AgentPresetRuntimeConfig:
    """AgentPreset 的运行期配置。

    - preset: 原始数据库记录
    - llm: llm_level 解析后的 LLMConfig
    - tools: tool 名称解析后的 callable 列表
    - tool_names: 原始工具名称列表，便于调试或回显
    - output_normalizer: 按 apid 注册的输出归一化函数（可为空）
    """

    preset: AgentPreset
    llm: LLMConfig
    tools: list[Callable[..., Any]]
    tool_names: list[str]
    output_normalizer: Optional[Callable[[str], str]] = None


def resolve_agent_preset(agent_preset: AgentPreset) -> AgentPresetRuntimeConfig:
    llm_config = llm_registry.require(agent_preset.llm_level)
    tool_names = list(agent_preset.tools)
    tools = [tool_registry.require(tool_name) for tool_name in tool_names]
    return AgentPresetRuntimeConfig(
        preset=agent_preset,
        llm=llm_config,
        tools=tools,
        tool_names=tool_names,
        output_normalizer=output_normalizer_registry.get(agent_preset.apid),
    )


def resolve_agent_preset_by_apid(manager: AgentPresetManager, apid: str) -> Optional[AgentPresetRuntimeConfig]:
    agent_preset = manager.get_agent_preset(apid)
    if agent_preset is None:
        return None
    return resolve_agent_preset(agent_preset)


def require_agent_preset_by_apid(manager: AgentPresetManager, apid: str) -> AgentPresetRuntimeConfig:
    resolved = resolve_agent_preset_by_apid(manager, apid)
    if resolved is None:
        raise ValueError(f"AgentPreset {apid} not found")
    return resolved


__all__ = [
    "AgentPresetRuntimeConfig",
    "resolve_agent_preset",
    "resolve_agent_preset_by_apid",
    "require_agent_preset_by_apid",
]