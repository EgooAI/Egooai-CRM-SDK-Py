import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import LLMApiConfigManager
from models import LLMApiConfig
from utils.common import bootstrap_engine


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _index_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()


def _columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


class MigrationTestCase(unittest.TestCase):
    def test_fresh_database_converges_to_target_schema(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "fresh.sqlite"
            _, engine = bootstrap_engine(db_path)
            try:
                self.assertNotIn(
                    "context_limit_output_text", _columns(db_path, "llm_api_config")
                )
                self.assertNotIn(
                    "tool_round_limit_output_text", _columns(db_path, "llm_api_config")
                )
                self.assertIn("created_at", _columns(db_path, "message"))
                self.assertIn("key", _columns(db_path, "sessionmeta"))
                self.assertIn("chat_history", _table_names(db_path))
                for index in (
                    "idx_message_sid",
                    "idx_session_meta_key",
                    "idx_account_mapping_type_key",
                    "idx_account_cid_pid_account",
                ):
                    self.assertIn(index, _index_names(db_path))

                conn = sqlite3.connect(db_path)
                try:
                    version = conn.execute(
                        "SELECT version FROM schema_version WHERE id = 1"
                    ).fetchone()
                finally:
                    conn.close()
                self.assertIsNotNone(version)
                self.assertGreaterEqual(int(version[0]), 1)
            finally:
                engine.dispose()

    def test_legacy_database_upgrades_in_place(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "legacy.sqlite"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "CREATE TABLE llm_api_config ("
                    "level INTEGER PRIMARY KEY, base_url TEXT NOT NULL, api_key TEXT NOT NULL, "
                    "model_name TEXT NOT NULL, system_prompt TEXT NOT NULL, context INTEGER NOT NULL, "
                    "context_limit_output_text TEXT NOT NULL, tool_round_limit_output_text TEXT NOT NULL, "
                    "max_tool_rounds INTEGER)"
                )
                conn.execute(
                    "INSERT INTO llm_api_config (level, base_url, api_key, model_name, system_prompt, "
                    "context, context_limit_output_text, tool_round_limit_output_text) "
                    "VALUES (0, 'u', 'k', 'm', '', 12000, 'ctx', 'tool')"
                )
                conn.execute(
                    "CREATE TABLE message ("
                    "external_mid TEXT PRIMARY KEY, sid INTEGER NOT NULL, sender INTEGER NOT NULL, "
                    "read BOOLEAN, content JSON NOT NULL, type TEXT NOT NULL)"
                )
                conn.execute(
                    "INSERT INTO message (external_mid, sid, sender, read, content, type) VALUES "
                    "('m1', 1, 1, NULL, '{\"created_at\": 1720000000, \"text\": \"hi\"}', 'text')"
                )
                conn.execute(
                    "INSERT INTO message (external_mid, sid, sender, read, content, type) VALUES "
                    "('m2', 1, 1, NULL, '{\"created_at\": \"2026-07-16T10:20:30\", \"text\": \"yo\"}', 'text')"
                )
                conn.execute(
                    "CREATE TABLE sessionmeta (sid INTEGER PRIMARY KEY, name VARCHAR, participants JSON NOT NULL)"
                )
                conn.execute(
                    "INSERT INTO sessionmeta (sid, name, participants) VALUES "
                    "(1, 'alibaba_icbu:self:contact', '[1,2]')"
                )
                conn.execute(
                    "CREATE TABLE message_test (id INTEGER PRIMARY KEY, name TEXT NOT NULL, content JSON NOT NULL)"
                )
                conn.execute(
                    "INSERT INTO message_test (id, name, content) VALUES (7, 'legacy chat', '{\"apid\":\"a\"}')"
                )
                conn.commit()
            finally:
                conn.close()

            _, engine = bootstrap_engine(db_path)
            try:
                self.assertNotIn(
                    "context_limit_output_text", _columns(db_path, "llm_api_config")
                )
                self.assertNotIn(
                    "tool_round_limit_output_text", _columns(db_path, "llm_api_config")
                )
                self.assertIn("created_at", _columns(db_path, "message"))
                self.assertIn("key", _columns(db_path, "sessionmeta"))
                self.assertNotIn("message_test", _table_names(db_path))
                self.assertIn("chat_history", _table_names(db_path))

                conn = sqlite3.connect(db_path)
                try:
                    config_row = conn.execute(
                        "SELECT base_url, max_tool_rounds FROM llm_api_config WHERE level = 0"
                    ).fetchone()
                    self.assertEqual(config_row[0], "u")

                    message_created = {
                        row[0]: row[1]
                        for row in conn.execute("SELECT external_mid, created_at FROM message")
                    }
                    self.assertIsNotNone(message_created["m1"])
                    self.assertIsNotNone(message_created["m2"])

                    session_key = conn.execute(
                        "SELECT key FROM sessionmeta WHERE sid = 1"
                    ).fetchone()
                    self.assertEqual(session_key[0], "alibaba_icbu:self:contact")

                    history_row = conn.execute(
                        "SELECT name, content FROM chat_history WHERE id = 7"
                    ).fetchone()
                    self.assertEqual(history_row[0], "legacy chat")
                    self.assertIn("apid", history_row[1])
                finally:
                    conn.close()

                manager = LLMApiConfigManager(database_path=db_path)
                try:
                    manager.replace_configs(
                        [
                            LLMApiConfig(
                                level=0,
                                base_url="https://api.example.com/v1",
                                api_key="replace-me",
                                model_name="example-model",
                                context=12000,
                            )
                        ]
                    )
                finally:
                    manager.engine.dispose()
            finally:
                engine.dispose()

    def test_migrations_are_idempotent_when_bootstrapped_twice(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "repeat.sqlite"
            _, engine = bootstrap_engine(db_path)
            engine.dispose()
            _, engine = bootstrap_engine(db_path)
            try:
                self.assertIn("created_at", _columns(db_path, "message"))
                self.assertIn("key", _columns(db_path, "sessionmeta"))
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()