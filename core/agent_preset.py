from typing import Optional

from models.agent_preset import AgentPreset, LLM_MAX_LEVEL

from .base import BaseManager


class AgentPresetManager(BaseManager[AgentPreset]):
    """负责 AgentPreset 表的连接初始化与增删改查操作。"""

    model = AgentPreset
    pk_field = "apid"
    editable_fields = ("name", "description", "prompt", "llm_level", "tools")
    pk_is_auto = False

    @staticmethod
    def _validate_apid(apid: str) -> None:
        if not apid:
            raise ValueError("apid must not be empty")

    @staticmethod
    def _validate_llm_level(llm_level: int) -> None:
        if not 0 <= llm_level <= LLM_MAX_LEVEL:
            raise ValueError("llm_level must be between 0 and %d" % LLM_MAX_LEVEL)

    def add_agent_preset(self, agent_preset: AgentPreset) -> None:
        self._validate_apid(agent_preset.apid)
        self._validate_llm_level(agent_preset.llm_level)
        self._add(agent_preset)

    def upsert_agent_preset(self, agent_preset: AgentPreset) -> None:
        self._validate_apid(agent_preset.apid)
        self._validate_llm_level(agent_preset.llm_level)
        self._upsert(agent_preset)

    def delete_agent_preset(self, apid: str) -> None:
        self._delete(apid)

    def edit_agent_preset(self, apid: str, agent_preset: AgentPreset) -> None:
        self._validate_llm_level(agent_preset.llm_level)
        self._edit(apid, agent_preset)

    def get_agent_preset(self, apid: str) -> Optional[AgentPreset]:
        return self._get(apid)

    def list_agent_preset(self) -> list[AgentPreset]:
        return self._list()


__all__ = ["AgentPresetManager"]
