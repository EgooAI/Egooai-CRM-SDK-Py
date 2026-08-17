import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import ChatHistoryManager
from models import ChatHistory


class ChatHistoryManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "chat_history.sqlite"
        self.manager = ChatHistoryManager(database_path=self.db_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.temp_dir.cleanup()

    def _build_chat_history(self, name: str = "测试对话") -> ChatHistory:
        return ChatHistory(
            name=name,
            content={
                "schema_version": 1,
                "apid": "agent-001",
                "agent_name": "测试 Agent",
                "messages": [
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "你好，有什么可以帮你？"},
                ],
                "created_at": "2026-07-16T10:20:30Z",
                "updated_at": "2026-07-16T10:22:00Z",
            },
        )

    def test_auto_creates_chat_history_table(self) -> None:
        self.assertTrue(self.db_path.exists())

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()

        self.assertIn("chat_history", tables)

    def test_add_chat_history_persists_generated_id(self) -> None:
        chat_history = self._build_chat_history()

        self.manager.add_chat_history(chat_history)

        self.assertIsNotNone(chat_history.id)

    def test_get_chat_history_returns_inserted_record(self) -> None:
        chat_history = self._build_chat_history()
        self.manager.add_chat_history(chat_history)

        saved_chat_history = self.manager.get_chat_history(chat_history.id)

        self.assertIsNotNone(saved_chat_history)
        assert saved_chat_history is not None
        self.assertEqual(saved_chat_history.name, "测试对话")
        self.assertEqual(saved_chat_history.content["apid"], "agent-001")
        self.assertEqual(saved_chat_history.content["messages"][0]["content"], "你好")

    def test_get_chat_history_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.get_chat_history(9999))

    def test_list_chat_history_returns_all_records_in_primary_key_order(self) -> None:
        first = self._build_chat_history("第一条")
        second = self._build_chat_history("第二条")
        self.manager.add_chat_history(first)
        self.manager.add_chat_history(second)

        histories = self.manager.list_chat_history()

        self.assertEqual([history.id for history in histories], [first.id, second.id])
        self.assertEqual([history.name for history in histories], ["第一条", "第二条"])

    def test_edit_chat_history_updates_fields(self) -> None:
        chat_history = self._build_chat_history()
        self.manager.add_chat_history(chat_history)
        updated = ChatHistory(
            name="更新后的对话",
            content={
                "schema_version": 1,
                "apid": "agent-001",
                "agent_name": "测试 Agent",
                "messages": [
                    {"role": "user", "content": "继续"},
                    {"role": "assistant", "content": "好的"},
                ],
                "created_at": "2026-07-16T10:20:30Z",
                "updated_at": "2026-07-16T10:25:00Z",
            },
        )

        self.manager.edit_chat_history(chat_history.id, updated)
        saved_chat_history = self.manager.get_chat_history(chat_history.id)

        self.assertIsNotNone(saved_chat_history)
        assert saved_chat_history is not None
        self.assertEqual(saved_chat_history.name, "更新后的对话")
        self.assertEqual(saved_chat_history.content["messages"][1]["content"], "好的")

    def test_edit_chat_history_raises_when_missing(self) -> None:
        updated = self._build_chat_history("missing")

        with self.assertRaises(ValueError):
            self.manager.edit_chat_history(9999, updated)

    def test_delete_chat_history_removes_record(self) -> None:
        chat_history = self._build_chat_history()
        self.manager.add_chat_history(chat_history)

        self.manager.delete_chat_history(chat_history.id)

        self.assertIsNone(self.manager.get_chat_history(chat_history.id))
        self.assertEqual(self.manager.list_chat_history(), [])

    def test_delete_chat_history_missing_is_no_op(self) -> None:
        self.manager.delete_chat_history(9999)
        self.assertEqual(self.manager.list_chat_history(), [])

    def test_upsert_chat_history_inserts_when_id_is_none(self) -> None:
        chat_history = self._build_chat_history("upsert-new")

        self.manager.upsert_chat_history(chat_history)

        self.assertIsNotNone(chat_history.id)
        self.assertEqual(len(self.manager.list_chat_history()), 1)

    def test_upsert_chat_history_updates_existing_fields(self) -> None:
        chat_history = self._build_chat_history("upsert-existing")
        self.manager.add_chat_history(chat_history)
        updated = ChatHistory(id=chat_history.id, name="upsert-updated", content={"messages": []})

        self.manager.upsert_chat_history(updated)
        saved_chat_history = self.manager.get_chat_history(chat_history.id)

        self.assertIsNotNone(saved_chat_history)
        assert saved_chat_history is not None
        self.assertEqual(saved_chat_history.name, "upsert-updated")
        self.assertEqual(saved_chat_history.content, {"messages": []})
        self.assertEqual(len(self.manager.list_chat_history()), 1)

    def test_upsert_chat_history_raises_when_explicit_id_is_missing(self) -> None:
        chat_history = ChatHistory(id=9999, name="missing", content={"messages": []})

        with self.assertRaises(ValueError):
            self.manager.upsert_chat_history(chat_history)


if __name__ == "__main__":
    unittest.main()