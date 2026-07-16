import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import MessageTestManager
from models import MessageTest


class MessageTestManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "message_test.sqlite"
        self.manager = MessageTestManager(database_path=self.db_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.temp_dir.cleanup()

    def _build_message_test(self, name: str = "测试对话") -> MessageTest:
        return MessageTest(
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

    def test_auto_creates_message_test_table(self) -> None:
        self.assertTrue(self.db_path.exists())

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()

        self.assertIn("Message_test", tables)

    def test_add_message_test_persists_generated_id(self) -> None:
        message_test = self._build_message_test()

        self.manager.add_message_test(message_test)

        self.assertIsNotNone(message_test.id)

    def test_get_message_test_returns_inserted_record(self) -> None:
        message_test = self._build_message_test()
        self.manager.add_message_test(message_test)

        saved_message_test = self.manager.get_message_test(message_test.id)

        self.assertIsNotNone(saved_message_test)
        assert saved_message_test is not None
        self.assertEqual(saved_message_test.name, "测试对话")
        self.assertEqual(saved_message_test.content["apid"], "agent-001")
        self.assertEqual(saved_message_test.content["messages"][0]["content"], "你好")

    def test_get_message_test_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.get_message_test(9999))

    def test_list_message_test_returns_all_records_in_primary_key_order(self) -> None:
        first = self._build_message_test("第一条")
        second = self._build_message_test("第二条")
        self.manager.add_message_test(first)
        self.manager.add_message_test(second)

        histories = self.manager.list_message_test()

        self.assertEqual([history.id for history in histories], [first.id, second.id])
        self.assertEqual([history.name for history in histories], ["第一条", "第二条"])

    def test_edit_message_test_updates_fields(self) -> None:
        message_test = self._build_message_test()
        self.manager.add_message_test(message_test)
        updated = MessageTest(
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

        self.manager.edit_message_test(message_test.id, updated)
        saved_message_test = self.manager.get_message_test(message_test.id)

        self.assertIsNotNone(saved_message_test)
        assert saved_message_test is not None
        self.assertEqual(saved_message_test.name, "更新后的对话")
        self.assertEqual(saved_message_test.content["messages"][1]["content"], "好的")

    def test_edit_message_test_raises_when_missing(self) -> None:
        updated = self._build_message_test("missing")

        with self.assertRaises(ValueError):
            self.manager.edit_message_test(9999, updated)

    def test_delete_message_test_removes_record(self) -> None:
        message_test = self._build_message_test()
        self.manager.add_message_test(message_test)

        self.manager.delete_message_test(message_test.id)

        self.assertIsNone(self.manager.get_message_test(message_test.id))
        self.assertEqual(self.manager.list_message_test(), [])

    def test_delete_message_test_missing_is_no_op(self) -> None:
        self.manager.delete_message_test(9999)
        self.assertEqual(self.manager.list_message_test(), [])

    def test_upsert_message_test_inserts_when_id_is_none(self) -> None:
        message_test = self._build_message_test("upsert-new")

        self.manager.upsert_message_test(message_test)

        self.assertIsNotNone(message_test.id)
        self.assertEqual(len(self.manager.list_message_test()), 1)

    def test_upsert_message_test_updates_existing_fields(self) -> None:
        message_test = self._build_message_test("upsert-existing")
        self.manager.add_message_test(message_test)
        updated = MessageTest(id=message_test.id, name="upsert-updated", content={"messages": []})

        self.manager.upsert_message_test(updated)
        saved_message_test = self.manager.get_message_test(message_test.id)

        self.assertIsNotNone(saved_message_test)
        assert saved_message_test is not None
        self.assertEqual(saved_message_test.name, "upsert-updated")
        self.assertEqual(saved_message_test.content, {"messages": []})
        self.assertEqual(len(self.manager.list_message_test()), 1)

    def test_upsert_message_test_raises_when_explicit_id_is_missing(self) -> None:
        message_test = MessageTest(id=9999, name="missing", content={"messages": []})

        with self.assertRaises(ValueError):
            self.manager.upsert_message_test(message_test)


if __name__ == "__main__":
    unittest.main()
