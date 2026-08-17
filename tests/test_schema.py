import sqlite3
import tempfile
import unittest
from pathlib import Path

import models  # noqa: F401  (register tables on SQLModel.metadata)
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

    def test_chat_history_table_exists(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='chat_history'"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)

    def test_no_schema_version_table(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()