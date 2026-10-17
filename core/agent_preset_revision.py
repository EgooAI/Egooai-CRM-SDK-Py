from typing import Optional

from sqlmodel import delete, select, Session

from models.agent_preset import LLM_MAX_LEVEL
from models.agent_preset_revision import AgentPresetRevision

from .base import BaseManager

DEFAULT_REVISION_LIMIT = 50


class AgentPresetRevisionManager(BaseManager[AgentPresetRevision]):
    """AgentPreset 历史快照的追加与查询；最新记录排在最前。"""

    model = AgentPresetRevision
    pk_field = "id"
    editable_fields = (
        "apid",
        "name",
        "description",
        "prompt",
        "llm_level",
        "tools",
        "source",
        "note",
    )
    pk_is_auto = True

    @staticmethod
    def _validate_llm_level(llm_level: int) -> None:
        if not 0 <= llm_level <= LLM_MAX_LEVEL:
            raise ValueError("llm_level must be between 0 and %d" % LLM_MAX_LEVEL)

    def add_revision(self, revision: AgentPresetRevision) -> None:
        self._validate_llm_level(revision.llm_level)
        self._add(revision)

    def get_revision(self, revision_id: int) -> Optional[AgentPresetRevision]:
        return self._get(revision_id)

    def list_revisions(
        self, apid: str, limit: int = DEFAULT_REVISION_LIMIT
    ) -> list[AgentPresetRevision]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")
        with Session(self.engine) as session:
            statement = (
                select(AgentPresetRevision)
                .where(AgentPresetRevision.apid == apid)
                .order_by(AgentPresetRevision.id.desc())
                .limit(limit)
            )
            return list(session.exec(statement).all())

    def prune_revisions(self, apid: str, keep: int = DEFAULT_REVISION_LIMIT) -> int:
        """保留最新的 ``keep`` 条记录，删除更早的快照；返回删除条数。"""
        if keep < 1:
            raise ValueError("keep must be greater than 0")
        with self._lock, Session(self.engine) as session:
            statement = (
                select(AgentPresetRevision.id)
                .where(AgentPresetRevision.apid == apid)
                .order_by(AgentPresetRevision.id.desc())
                .offset(keep)
            )
            stale_ids = list(session.exec(statement).all())
            if not stale_ids:
                return 0
            session.exec(
                delete(AgentPresetRevision).where(AgentPresetRevision.id.in_(stale_ids))
            )
            session.commit()
            return len(stale_ids)


__all__ = ["AgentPresetRevisionManager", "DEFAULT_REVISION_LIMIT"]
