import sqlite3
import tempfile
import unittest
from pathlib import Path

import models  # noqa: F401  (register tables on SQLModel.metadata)
from core import AgentPresetManager
from utils.common import bootstrap_engine


class SchemaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "schema.sqlite"
        _, self.engine = bootstrap_engine(self.db_path)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _index_list(self, table: str) -> list[tuple[str, int]]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
        finally:
            conn.close()
        return [(row[1], row[2]) for row in rows]

    def _index_names(self, table: str) -> set[str]:
        return {name for name, _ in self._index_list(table)}

    def test_message_has_sid_and_sender_indexes(self) -> None:
        indexes = self._index_names("message")
        self.assertIn("ix_message_sid", indexes)
        self.assertIn("ix_message_sender", indexes)

    def test_session_meta_key_index_is_unique(self) -> None:
        indexes = dict(self._index_list("session_meta"))
        self.assertEqual(indexes["ix_session_meta_key"], 1)

    def test_account_mapping_composite_index(self) -> None:
        self.assertIn("idx_account_mapping_type_key", self._index_names("accountmapping"))

    def test_account_composite_index(self) -> None:
        self.assertIn("idx_account_cid_pid_account", self._index_names("account"))

    def test_bootstrap_preserves_sdk_table_names_without_schema_version_table(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        self.assertTrue({
            "account", "accountmapping", "agentpreset", "agent_preset_revision", "chat_history", "customer",
            "llm_api_config", "message", "meta", "platform", "session_meta", "translate",
        }.issubset(tables))
        self.assertNotIn("schema_version", tables)

    def test_bootstrap_adds_enabled_column_to_legacy_agent_preset(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.sqlite"
        conn = sqlite3.connect(legacy_path)
        try:
            conn.execute(
                "CREATE TABLE agentpreset (apid TEXT PRIMARY KEY, name TEXT, description TEXT, "
                "prompt TEXT, llm_level INTEGER, tools JSON)"
            )
            conn.execute(
                "INSERT INTO agentpreset VALUES ('agent-legacy', 'A', 'D', 'P', 1, '[\"calculator\"]')"
            )
            conn.commit()
        finally:
            conn.close()

        _, engine = bootstrap_engine(legacy_path)
        try:
            manager = AgentPresetManager(database_path=legacy_path)
            preset = manager.get_agent_preset("agent-legacy")
            self.assertIsNotNone(preset)
            assert preset is not None
            self.assertTrue(preset.enabled)
            preset.enabled = False
            manager.upsert_agent_preset(preset)
            self.assertFalse(manager.get_agent_preset("agent-legacy").enabled)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
