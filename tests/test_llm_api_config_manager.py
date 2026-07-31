import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import LLMApiConfigManager
from models import LLMApiConfig


class LLMApiConfigManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "llm_api_config.sqlite"
        self.manager = LLMApiConfigManager(database_path=self.db_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.temp_dir.cleanup()

    def test_auto_creates_llm_api_config_table(self) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            columns = {row[1] for row in connection.execute("PRAGMA table_info(llm_api_config)")}
        finally:
            connection.close()

        self.assertIn("llm_api_config", tables)
        self.assertNotIn("context_limit_output_text", columns)
        self.assertNotIn("tool_round_limit_output_text", columns)

    def test_to_payload_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.to_payload())

    def test_upsert_config_inserts_and_updates_level(self) -> None:
        config = LLMApiConfig(
            level=0,
            base_url="https://api.example.com",
            api_key="secret",
            model_name="example-model",
            system_prompt="system",
            context=12000,
            max_tool_rounds=5,
        )

        self.manager.upsert_config(config)
        saved = self.manager.get_config(0)
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertEqual(saved.model_name, "example-model")

        updated = LLMApiConfig(
            level=0,
            base_url="https://api.example.com",
            api_key="secret",
            model_name="updated-model",
            context=12000,
        )
        self.manager.upsert_config(updated)

        saved = self.manager.get_config(0)
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertEqual(saved.model_name, "updated-model")

    def test_replace_configs_and_to_payload(self) -> None:
        self.manager.replace_configs(
            [
                LLMApiConfig(
                    level=0,
                    base_url="https://api.example.com",
                    api_key="secret",
                    model_name="model-a",
                    context=12000,
                ),
                LLMApiConfig(
                    level=1,
                    base_url="https://api.example.com",
                    api_key="secret",
                    model_name="model-b",
                    context=8000,
                    max_tool_rounds=3,
                ),
            ]
        )

        payload = self.manager.to_payload()
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["levels"][0]["model_name"], "model-a")
        self.assertEqual(payload["levels"][1]["max_tool_rounds"], 3)
        self.assertNotIn("context_limit_output_text", payload["levels"][0])
        self.assertNotIn("tool_round_limit_output_text", payload["levels"][0])

    def test_manager_migrates_legacy_output_text_columns(self) -> None:
        self.manager.engine.dispose()
        legacy_db_path = self.temp_path / "legacy_llm_api_config.sqlite"
        connection = sqlite3.connect(legacy_db_path)
        try:
            connection.execute(
                """
                CREATE TABLE llm_api_config (
                    level INTEGER NOT NULL PRIMARY KEY,
                    base_url VARCHAR NOT NULL,
                    api_key VARCHAR NOT NULL,
                    model_name VARCHAR NOT NULL,
                    system_prompt VARCHAR NOT NULL,
                    context INTEGER NOT NULL,
                    context_limit_output_text VARCHAR NOT NULL,
                    tool_round_limit_output_text VARCHAR NOT NULL,
                    max_tool_rounds INTEGER
                )
                """
            )
            connection.execute(
                """
                INSERT INTO llm_api_config (
                    level,
                    base_url,
                    api_key,
                    model_name,
                    system_prompt,
                    context,
                    context_limit_output_text,
                    tool_round_limit_output_text,
                    max_tool_rounds
                )
                VALUES (0, 'https://api.example.com', 'secret', 'legacy-model', '', 12000, 'context', 'tool', 5)
                """
            )
            connection.commit()
        finally:
            connection.close()

        manager = LLMApiConfigManager(database_path=legacy_db_path)
        try:
            saved = manager.get_config(0)
            self.assertIsNotNone(saved)
            assert saved is not None
            self.assertEqual(saved.model_name, "legacy-model")
            connection = sqlite3.connect(legacy_db_path)
            try:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(llm_api_config)")}
            finally:
                connection.close()
            self.assertNotIn("context_limit_output_text", columns)
            self.assertNotIn("tool_round_limit_output_text", columns)
        finally:
            manager.engine.dispose()


if __name__ == "__main__":
    unittest.main()
