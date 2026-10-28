from typing import Optional

from sqlmodel import Session, select

from models.chat_history import ChatHistory
from models.experiment import Experiment

from .base import BaseManager

MAX_VARIANTS_PER_EXPERIMENT = 4


class ExperimentManager(BaseManager[Experiment]):
    """Experiments and the ``ChatHistory`` rows that serve as their variants.

    A session belongs to at most one experiment. Attaching is idempotent; the
    manager enforces only the structural rules (existence, single ownership,
    variant cap). Deleting an experiment detaches its variants instead of
    deleting them, so sessions stay readable.
    """

    model = Experiment
    pk_field = "id"
    editable_fields = ("agent_id", "name", "content")
    touch_updated_time = True
    pk_is_auto = True

    def add_experiment(self, experiment: Experiment) -> None:
        self._add(experiment)

    def get_experiment(self, experiment_id: int) -> Optional[Experiment]:
        return self._get(experiment_id)

    def edit_experiment(self, experiment_id: int, experiment: Experiment) -> None:
        self._edit(experiment_id, experiment)

    def list_experiments(self, agent_id: Optional[str] = None) -> list[Experiment]:
        """Return experiments newest first, optionally for one agent."""
        with Session(self.engine) as session:
            statement = select(Experiment)
            if agent_id is not None:
                statement = statement.where(Experiment.agent_id == agent_id)
            statement = statement.order_by(Experiment.id.desc())
            return list(session.exec(statement).all())

    def delete_experiment(self, experiment_id: int) -> None:
        """Delete the experiment; its sessions survive and become standalone."""
        with self._lock, Session(self.engine) as session:
            current = session.get(Experiment, experiment_id)
            if current is None:
                return
            for variant in session.exec(
                select(ChatHistory).where(ChatHistory.experiment_id == experiment_id)
            ):
                variant.experiment_id = None
                session.add(variant)
            session.delete(current)
            session.commit()

    def attach_variant(
        self,
        experiment_id: int,
        session_id: int,
        *,
        max_variants: int = MAX_VARIANTS_PER_EXPERIMENT,
    ) -> None:
        """Make ``session_id`` a variant of the experiment."""
        if max_variants < 1:
            raise ValueError("max_variants must be greater than 0")
        with self._lock, Session(self.engine) as session:
            if session.get(Experiment, experiment_id) is None:
                raise ValueError(f"Experiment {experiment_id} not found")
            variant = session.get(ChatHistory, session_id)
            if variant is None:
                raise ValueError(f"ChatHistory {session_id} not found")
            if variant.experiment_id == experiment_id:
                return
            if variant.experiment_id is not None:
                raise ValueError(
                    f"ChatHistory {session_id} already belongs to experiment "
                    f"{variant.experiment_id}"
                )
            attached = len(session.exec(
                select(ChatHistory.id).where(ChatHistory.experiment_id == experiment_id)
            ).all())
            if attached >= max_variants:
                raise ValueError(
                    f"An experiment holds at most {max_variants} variants"
                )
            variant.experiment_id = experiment_id
            session.add(variant)
            session.commit()

    def detach_variant(self, session_id: int) -> None:
        with self._lock, Session(self.engine) as session:
            variant = session.get(ChatHistory, session_id)
            if variant is None or variant.experiment_id is None:
                return
            variant.experiment_id = None
            session.add(variant)
            session.commit()

    def list_variants(self, experiment_id: int) -> list[ChatHistory]:
        """Variants in creation order; the first one is the baseline."""
        with Session(self.engine) as session:
            statement = (
                select(ChatHistory)
                .where(ChatHistory.experiment_id == experiment_id)
                .order_by(ChatHistory.id)
            )
            return list(session.exec(statement).all())

    def experiment_of(self, session_id: int) -> Optional[int]:
        with Session(self.engine) as session:
            variant = session.get(ChatHistory, session_id)
            return None if variant is None else variant.experiment_id


__all__ = ["ExperimentManager", "MAX_VARIANTS_PER_EXPERIMENT"]
