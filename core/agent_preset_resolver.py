from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

from core.agent_preset import AgentPresetManager
from core.registry import LLMConfig, llm_registry, tool_registry
from core.system_agent_tools import SYSTEM_AGENT_ONLY_TOOLS, SYSTEM_AGENT_TOOLS
from models.agent_preset import AgentPreset


@dataclass(frozen=True)
class AgentPresetRuntimeConfig:
    """AgentPreset 的运行期配置。

    - preset: 原始数据库记录
    - llm: intelevel 解析后的 LLMConfig
    - tools: tool 名称解析后的 callable 列表
    - tool_names: 原始工具名称列表，便于调试或回显
    """

    preset: AgentPreset
    llm: LLMConfig
    tools: list[Callable[..., Any]]
    tool_names: list[str]


class AgentPresetResolver:
    """负责把持久化的 AgentPreset 解析为运行期配置。"""

    @staticmethod
    def resolve(agent_preset: AgentPreset) -> AgentPresetRuntimeConfig:
        llm_config = llm_registry.require(agent_preset.intelevel)
        if agent_preset.apid in SYSTEM_AGENT_TOOLS:
            tool_names = list(SYSTEM_AGENT_TOOLS[agent_preset.apid])
        else:
            tool_names = list(agent_preset.tools)
            forbidden_tools = sorted(SYSTEM_AGENT_ONLY_TOOLS.intersection(tool_names))
            if forbidden_tools:
                raise ValueError(
                    "普通 Agent 不能调用系统 Chat 工具: "
                    + ", ".join(forbidden_tools)
                )
        tools = [tool_registry.require(tool_name) for tool_name in tool_names]
        return AgentPresetRuntimeConfig(
            preset=agent_preset,
            llm=llm_config,
            tools=tools,
            tool_names=tool_names,
        )

    def resolve_by_apid(self, manager: AgentPresetManager, apid: str) -> Optional[AgentPresetRuntimeConfig]:
        agent_preset = manager.get_agent_preset(apid)
        if agent_preset is None:
            return None
        return self.resolve(agent_preset)

    def require_by_apid(self, manager: AgentPresetManager, apid: str) -> AgentPresetRuntimeConfig:
        resolved = self.resolve_by_apid(manager, apid)
        if resolved is None:
            raise ValueError(f"AgentPreset {apid} not found")
        return resolved


agent_preset_resolver = AgentPresetResolver()


def resolve_agent_preset(agent_preset: AgentPreset) -> AgentPresetRuntimeConfig:
    return agent_preset_resolver.resolve(agent_preset)


def resolve_agent_preset_by_apid(manager: AgentPresetManager, apid: str) -> Optional[AgentPresetRuntimeConfig]:
    return agent_preset_resolver.resolve_by_apid(manager, apid)


def require_agent_preset_by_apid(manager: AgentPresetManager, apid: str) -> AgentPresetRuntimeConfig:
    return agent_preset_resolver.require_by_apid(manager, apid)


__all__ = [
    "AgentPresetRuntimeConfig",
    "AgentPresetResolver",
    "agent_preset_resolver",
    "resolve_agent_preset",
    "resolve_agent_preset_by_apid",
    "require_agent_preset_by_apid",
]
