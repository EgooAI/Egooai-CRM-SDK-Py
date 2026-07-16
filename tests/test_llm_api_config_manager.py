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
        finally:
            connection.close()

        self.assertIn("llm_api_config", tables)

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
            context_limit_output_text="context limit",
            tool_round_limit_output_text="tool limit",
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


if __name__ == "__main__":
    unittest.main()
