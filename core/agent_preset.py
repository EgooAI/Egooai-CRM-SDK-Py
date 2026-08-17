from pathlib import Path
from typing import Optional

from sqlalchemy import inspect
from sqlmodel import Session, select

from models.agent_preset import AgentPreset, LLM_MAX_LEVEL
from utils.common import bootstrap_engine, get_database_lock


class AgentPresetManager:
    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        self.database_path, self.engine = bootstrap_engine(database_path)
        self._lock = get_database_lock(self.database_path)

    @staticmethod
    def _validate_apid(apid: str) -> None:
        if not apid:
            raise ValueError("apid must not be empty")

    @staticmethod
    def _validate_llm_level(llm_level: int) -> None:
        if not 0 <= llm_level <= LLM_MAX_LEVEL:
            raise ValueError("llm_level must be between 0 and %d" % LLM_MAX_LEVEL)

    @staticmethod
    def _payload_tuple(agent_preset: AgentPreset) -> tuple[object, ...]:
        return (
            agent_preset.name,
            agent_preset.description,
            agent_preset.prompt,
            agent_preset.llm_level,
            agent_preset.tools,
        )

    @staticmethod
    def _apply_agent_preset_updates(current_agent_preset: AgentPreset, agent_preset: AgentPreset) -> None:
        current_agent_preset.name = agent_preset.name
        current_agent_preset.description = agent_preset.description
        current_agent_preset.prompt = agent_preset.prompt
        current_agent_preset.llm_level = agent_preset.llm_level
        current_agent_preset.tools = agent_preset.tools

    def add_agent_preset(self, agent_preset: AgentPreset) -> None:
        self._validate_apid(agent_preset.apid)
        self._validate_llm_level(agent_preset.llm_level)

        with self._lock:
            with Session(self.engine) as session:
                session.add(agent_preset)
                session.commit()
                session.refresh(agent_preset)

    def upsert_agent_preset(self, agent_preset: AgentPreset) -> None:
        self._validate_apid(agent_preset.apid)
        self._validate_llm_level(agent_preset.llm_level)

        with self._lock:
            with Session(self.engine) as session:
                current_agent_preset = session.get(AgentPreset, agent_preset.apid)
                if current_agent_preset is None:
                    session.add(agent_preset)
                    session.commit()
                    session.refresh(agent_preset)
                    return

                if self._payload_tuple(current_agent_preset) == self._payload_tuple(agent_preset):
                    return

                self._apply_agent_preset_updates(current_agent_preset, agent_preset)
                session.add(current_agent_preset)
                session.commit()
                session.refresh(current_agent_preset)

    def delete_agent_preset(self, apid: str) -> None:
        with self._lock:
            with Session(self.engine) as session:
                current_agent_preset = session.get(AgentPreset, apid)
                if current_agent_preset is None:
                    return

                session.delete(current_agent_preset)
                session.commit()

    def edit_agent_preset(self, apid: str, agent_preset: AgentPreset) -> None:
        self._validate_llm_level(agent_preset.llm_level)

        with self._lock:
            with Session(self.engine) as session:
                current_agent_preset = session.get(AgentPreset, apid)
                if current_agent_preset is None:
                    raise ValueError(f"AgentPreset {apid} not found")

                self._apply_agent_preset_updates(current_agent_preset, agent_preset)

                session.add(current_agent_preset)
                session.commit()
                session.refresh(current_agent_preset)

    def get_agent_preset(self, apid: str) -> Optional[AgentPreset]:
        with Session(self.engine) as session:
            return session.get(AgentPreset, apid)

    def list_agent_preset(self) -> list[AgentPreset]:
        with Session(self.engine) as session:
            apid_column = inspect(AgentPreset).columns.apid
            statement = select(AgentPreset).order_by(apid_column)
            return list(session.exec(statement).all())


__all__ = ["AgentPresetManager"]
