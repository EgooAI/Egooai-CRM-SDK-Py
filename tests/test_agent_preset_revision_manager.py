import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import AgentPresetManager, AgentPresetRevisionManager
from models import AgentPreset, AgentPresetRevision


class AgentPresetRevisionManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "agent_preset_revision.sqlite"
        self.preset_manager = AgentPresetManager(database_path=self.db_path)
        self.manager = AgentPresetRevisionManager(database_path=self.db_path)
        self.preset_manager.upsert_agent_preset(self._build_preset())

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.temp_dir.cleanup()

    @staticmethod
    def _build_preset(apid: str = "agent-history") -> AgentPreset:
        return AgentPreset(
            apid=apid,
            name="History Agent",
            description="Preset under revision tracking",
            prompt="initial prompt",
            llm_level=1,
            tools=["calculator"],
        )

    @staticmethod
    def _build_revision(
        apid: str = "agent-history",
        prompt: str = "initial prompt",
        source: str = "manual",
        note: str = "",
        llm_level: int = 1,
    ) -> AgentPresetRevision:
        return AgentPresetRevision(
            apid=apid,
            name="History Agent",
            description="Preset under revision tracking",
            prompt=prompt,
            llm_level=llm_level,
            tools=["calculator"],
            source=source,
            note=note,
        )

    def test_add_revision_roundtrip_and_default_timestamp(self) -> None:
        revision = self._build_revision(prompt="first save", source="ai", note="更简洁")

        self.manager.add_revision(revision)

        self.assertIsNotNone(revision.id)
        saved = self.manager.get_revision(revision.id)
        assert saved is not None
        self.assertEqual(saved.apid, "agent-history")
        self.assertEqual(saved.prompt, "first save")
        self.assertEqual(saved.tools, ["calculator"])
        self.assertEqual(saved.source, "ai")
        self.assertEqual(saved.note, "更简洁")
        self.assertIsNotNone(saved.created_time)

    def test_get_revision_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.get_revision(999))

    def test_list_revisions_returns_newest_first_and_filters_by_apid(self) -> None:
        self.preset_manager.upsert_agent_preset(self._build_preset(apid="agent-other"))
        first = self._build_revision(prompt="v1")
        second = self._build_revision(prompt="v2")
        other = self._build_revision(apid="agent-other", prompt="other")
        for revision in (first, second, other):
            self.manager.add_revision(revision)

        revisions = self.manager.list_revisions("agent-history")

        self.assertEqual([revision.prompt for revision in revisions], ["v2", "v1"])
        self.assertEqual(
            [revision.apid for revision in revisions], ["agent-history", "agent-history"]
        )

    def test_list_revisions_honors_limit(self) -> None:
        for index in range(3):
            self.manager.add_revision(self._build_revision(prompt=f"v{index}"))

        self.assertEqual(len(self.manager.list_revisions("agent-history", limit=2)), 2)
        with self.assertRaises(ValueError):
            self.manager.list_revisions("agent-history", limit=0)

    def test_prune_revisions_keeps_newest(self) -> None:
        for index in range(5):
            self.manager.add_revision(self._build_revision(prompt=f"v{index}"))

        removed = self.manager.prune_revisions("agent-history", keep=2)

        self.assertEqual(removed, 3)
        remaining = self.manager.list_revisions("agent-history")
        self.assertEqual([revision.prompt for revision in remaining], ["v4", "v3"])
        self.assertEqual(self.manager.prune_revisions("agent-history", keep=2), 0)
        with self.assertRaises(ValueError):
            self.manager.prune_revisions("agent-history", keep=0)

    def test_deleting_preset_cascades_its_revisions(self) -> None:
        self.manager.add_revision(self._build_revision())
        self.preset_manager.upsert_agent_preset(self._build_preset(apid="agent-other"))
        self.manager.add_revision(self._build_revision(apid="agent-other"))

        self.preset_manager.delete_agent_preset("agent-history")

        self.assertEqual(self.manager.list_revisions("agent-history"), [])
        self.assertEqual(len(self.manager.list_revisions("agent-other")), 1)

    def test_add_revision_rejects_unknown_llm_level(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.add_revision(self._build_revision(llm_level=5))


if __name__ == "__main__":
    unittest.main()
