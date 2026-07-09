import sqlite3
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import AgentPresetManager
from models import AgentPreset


class AgentPresetManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "agent_preset.sqlite"
        self.manager = AgentPresetManager(database_path=self.db_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.temp_dir.cleanup()

    def _build_agent_preset(
        self,
        name: str = "default assistant",
        description: str = "General customer service preset",
        prompt: str = "Help the customer politely",
        intelevel: int = 2,
        tools: list[str] | None = None,
    ) -> AgentPreset:
        payload = {
            "name": name,
            "description": description,
            "prompt": prompt,
            "intelevel": intelevel,
        }
        if tools is not None:
            payload["tools"] = tools
        return AgentPreset(**payload)

    def test_auto_creates_agent_preset_table(self) -> None:
        self.assertTrue(self.db_path.exists())

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()

        self.assertIn("agentpreset", tables)

    def test_add_agent_preset_populates_primary_key(self) -> None:
        agent_preset = self._build_agent_preset()

        self.manager.add_agent_preset(agent_preset)

        self.assertIsNotNone(agent_preset.apid)

    def test_get_agent_preset_returns_inserted_record(self) -> None:
        agent_preset = self._build_agent_preset(tools=["web_search", "calculator"])
        self.manager.add_agent_preset(agent_preset)

        saved_agent_preset = self.manager.get_agent_preset(agent_preset.apid)

        self.assertIsNotNone(saved_agent_preset)
        assert saved_agent_preset is not None
        self.assertEqual(saved_agent_preset.name, "default assistant")
        self.assertEqual(saved_agent_preset.description, "General customer service preset")
        self.assertEqual(saved_agent_preset.prompt, "Help the customer politely")
        self.assertEqual(saved_agent_preset.intelevel, 2)
        self.assertEqual(saved_agent_preset.tools, ["web_search", "calculator"])

    def test_get_agent_preset_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.get_agent_preset(9999))

    def test_add_agent_preset_defaults_tools_to_empty_list(self) -> None:
        agent_preset = self._build_agent_preset()

        self.manager.add_agent_preset(agent_preset)
        saved_agent_preset = self.manager.get_agent_preset(agent_preset.apid)

        self.assertIsNotNone(saved_agent_preset)
        assert saved_agent_preset is not None
        self.assertEqual(saved_agent_preset.tools, [])

    def test_list_agent_preset_returns_all_records_in_apid_order(self) -> None:
        first = self._build_agent_preset(name="preset-a", intelevel=1)
        second = self._build_agent_preset(name="preset-b", intelevel=3, tools=["browser"])

        self.manager.add_agent_preset(first)
        self.manager.add_agent_preset(second)

        agent_presets = self.manager.list_agent_preset()

        self.assertEqual([item.apid for item in agent_presets], [first.apid, second.apid])
        self.assertEqual([item.name for item in agent_presets], ["preset-a", "preset-b"])

    def test_edit_agent_preset_updates_fields(self) -> None:
        agent_preset = self._build_agent_preset()
        self.manager.add_agent_preset(agent_preset)

        updated_agent_preset = AgentPreset(
            name="sales closer",
            description="Preset for closing enterprise leads",
            prompt="Convert qualified leads into contracts",
            intelevel=4,
            tools=["crm_lookup", "calendar"],
        )

        self.manager.edit_agent_preset(agent_preset.apid, updated_agent_preset)
        saved_agent_preset = self.manager.get_agent_preset(agent_preset.apid)

        self.assertIsNotNone(saved_agent_preset)
        assert saved_agent_preset is not None
        self.assertEqual(saved_agent_preset.apid, agent_preset.apid)
        self.assertEqual(saved_agent_preset.name, "sales closer")
        self.assertEqual(saved_agent_preset.description, "Preset for closing enterprise leads")
        self.assertEqual(saved_agent_preset.prompt, "Convert qualified leads into contracts")
        self.assertEqual(saved_agent_preset.intelevel, 4)
        self.assertEqual(saved_agent_preset.tools, ["crm_lookup", "calendar"])

    def test_edit_agent_preset_raises_when_missing(self) -> None:
        updated_agent_preset = self._build_agent_preset()

        with self.assertRaises(ValueError):
            self.manager.edit_agent_preset(404, updated_agent_preset)

    def test_delete_agent_preset_removes_record(self) -> None:
        agent_preset = self._build_agent_preset()
        self.manager.add_agent_preset(agent_preset)

        self.manager.delete_agent_preset(agent_preset.apid)

        self.assertIsNone(self.manager.get_agent_preset(agent_preset.apid))
        self.assertEqual(self.manager.list_agent_preset(), [])

    def test_delete_agent_preset_missing_is_no_op(self) -> None:
        self.manager.delete_agent_preset(404)
        self.assertEqual(self.manager.list_agent_preset(), [])

    def test_add_agent_preset_rejects_intelevel_below_zero(self) -> None:
        agent_preset = self._build_agent_preset(intelevel=-1)

        with self.assertRaises(ValueError):
            self.manager.add_agent_preset(agent_preset)

    def test_add_agent_preset_rejects_intelevel_above_four(self) -> None:
        agent_preset = self._build_agent_preset(intelevel=5)

        with self.assertRaises(ValueError):
            self.manager.add_agent_preset(agent_preset)

    def test_edit_agent_preset_rejects_invalid_intelevel(self) -> None:
        agent_preset = self._build_agent_preset()
        self.manager.add_agent_preset(agent_preset)
        updated_agent_preset = self._build_agent_preset(intelevel=9)

        with self.assertRaises(ValueError):
            self.manager.edit_agent_preset(agent_preset.apid, updated_agent_preset)

    def test_upsert_agent_preset_inserts_when_missing(self) -> None:
        agent_preset = self._build_agent_preset(name="preset-upsert")

        self.manager.upsert_agent_preset(agent_preset)

        self.assertIsNotNone(agent_preset.apid)
        self.assertEqual(len(self.manager.list_agent_preset()), 1)

    def test_upsert_agent_preset_updates_existing_fields(self) -> None:
        agent_preset = self._build_agent_preset()
        self.manager.add_agent_preset(agent_preset)
        updated_agent_preset = AgentPreset(
            apid=agent_preset.apid,
            name="preset-updated",
            description="Updated preset",
            prompt="Use the updated prompt",
            intelevel=4,
            tools=["calendar"],
        )

        self.manager.upsert_agent_preset(updated_agent_preset)
        saved_agent_preset = self.manager.get_agent_preset(agent_preset.apid)

        self.assertIsNotNone(saved_agent_preset)
        assert saved_agent_preset is not None
        self.assertEqual(saved_agent_preset.name, "preset-updated")
        self.assertEqual(saved_agent_preset.tools, ["calendar"])

    def test_upsert_agent_preset_skips_duplicate_payload_without_primary_key(self) -> None:
        agent_preset = self._build_agent_preset()
        self.manager.add_agent_preset(agent_preset)
        duplicate_agent_preset = self._build_agent_preset()

        self.manager.upsert_agent_preset(duplicate_agent_preset)

        self.assertEqual(len(self.manager.list_agent_preset()), 1)
        self.assertEqual(duplicate_agent_preset.apid, agent_preset.apid)

    def test_upsert_agent_preset_raises_when_explicit_primary_key_missing(self) -> None:
        missing_agent_preset = AgentPreset(
            apid=999,
            name="ghost",
            description="missing preset",
            prompt="ghost prompt",
            intelevel=1,
            tools=[],
        )

        with self.assertRaises(ValueError):
            self.manager.upsert_agent_preset(missing_agent_preset)

    def test_upsert_agent_preset_rejects_invalid_intelevel(self) -> None:
        invalid_agent_preset = self._build_agent_preset(intelevel=5)

        with self.assertRaises(ValueError):
            self.manager.upsert_agent_preset(invalid_agent_preset)

    def test_concurrent_upsert_agent_preset_skips_duplicate_payload(self) -> None:
        errors: list[BaseException] = []

        def _worker() -> None:
            try:
                self.manager.upsert_agent_preset(self._build_agent_preset())
            except BaseException as exc:  # pragma: no cover - test captures thread failures
                errors.append(exc)

        threads = [threading.Thread(target=_worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(self.manager.list_agent_preset()), 1)


if __name__ == "__main__":
    unittest.main()
