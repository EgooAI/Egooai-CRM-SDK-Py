import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import ChatHistoryManager, ExperimentManager, MAX_VARIANTS_PER_EXPERIMENT
from models import ChatHistory, Experiment


class ExperimentManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "experiment.sqlite"
        self.experiments = ExperimentManager(database_path=self.db_path)
        self.sessions = ChatHistoryManager(database_path=self.db_path)

    def tearDown(self) -> None:
        self.experiments.engine.dispose()
        self.temp_dir.cleanup()

    def _experiment(self, name: str = "tuning") -> Experiment:
        experiment = Experiment(agent_id="agent-1", name=name, content={"frozen": "prefix"})
        self.experiments.add_experiment(experiment)
        return experiment

    def _session(self, name: str = "variant") -> ChatHistory:
        session = ChatHistory(name=name, content={"messages": []})
        self.sessions.add_chat_history(session)
        return session

    def test_add_and_get_roundtrip_keeps_opaque_content(self) -> None:
        experiment = self._experiment()

        saved = self.experiments.get_experiment(experiment.id)

        assert saved is not None
        self.assertEqual(saved.agent_id, "agent-1")
        self.assertEqual(saved.content, {"frozen": "prefix"})
        self.assertIsNotNone(saved.created_time)

    def test_get_missing_experiment_returns_none(self) -> None:
        self.assertIsNone(self.experiments.get_experiment(999))

    def test_list_experiments_filters_by_agent_newest_first(self) -> None:
        first = self._experiment("first")
        second = self._experiment("second")
        other = Experiment(agent_id="agent-2", name="other", content={})
        self.experiments.add_experiment(other)

        listed = self.experiments.list_experiments("agent-1")

        self.assertEqual([item.id for item in listed], [second.id, first.id])
        self.assertEqual([item.id for item in self.experiments.list_experiments()],
                         [other.id, second.id, first.id])

    def test_attach_makes_session_a_variant_and_is_idempotent(self) -> None:
        experiment = self._experiment()
        session = self._session()

        self.experiments.attach_variant(experiment.id, session.id)
        self.experiments.attach_variant(experiment.id, session.id)

        self.assertEqual([item.id for item in self.experiments.list_variants(experiment.id)],
                         [session.id])
        self.assertEqual(self.experiments.experiment_of(session.id), experiment.id)

    def test_attach_rejects_a_session_owned_by_another_experiment(self) -> None:
        first = self._experiment()
        second = self._experiment("other")
        session = self._session()
        self.experiments.attach_variant(first.id, session.id)

        with self.assertRaises(ValueError):
            self.experiments.attach_variant(second.id, session.id)

    def test_attach_rejects_missing_rows(self) -> None:
        experiment = self._experiment()
        with self.assertRaises(ValueError):
            self.experiments.attach_variant(experiment.id, 999)
        with self.assertRaises(ValueError):
            self.experiments.attach_variant(999, self._session().id)

    def test_attach_enforces_variant_cap(self) -> None:
        experiment = self._experiment()
        for _ in range(MAX_VARIANTS_PER_EXPERIMENT):
            self.experiments.attach_variant(experiment.id, self._session().id)

        with self.assertRaises(ValueError):
            self.experiments.attach_variant(experiment.id, self._session().id)

    def test_detach_returns_session_to_standalone(self) -> None:
        experiment = self._experiment()
        session = self._session()
        self.experiments.attach_variant(experiment.id, session.id)

        self.experiments.detach_variant(session.id)

        self.assertIsNone(self.experiments.experiment_of(session.id))
        self.assertEqual(self.experiments.list_variants(experiment.id), [])

    def test_deleting_experiment_keeps_its_sessions_readable(self) -> None:
        experiment = self._experiment()
        session = self._session()
        self.experiments.attach_variant(experiment.id, session.id)

        self.experiments.delete_experiment(experiment.id)

        self.assertIsNone(self.experiments.get_experiment(experiment.id))
        self.assertIsNone(self.experiments.experiment_of(session.id))
        self.assertIsNotNone(self.sessions.get_chat_history(session.id))

    def test_edit_updates_name_and_refreshes_updated_time(self) -> None:
        experiment = self._experiment("before")

        self.experiments.edit_experiment(
            experiment.id, Experiment(agent_id="agent-1", name="after", content={"a": 1})
        )

        saved = self.experiments.get_experiment(experiment.id)
        assert saved is not None
        self.assertEqual(saved.name, "after")
        self.assertEqual(saved.content, {"a": 1})
        self.assertGreaterEqual(saved.updated_time, saved.created_time)


if __name__ == "__main__":
    unittest.main()
