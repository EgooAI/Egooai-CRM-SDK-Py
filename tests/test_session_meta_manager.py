import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core import SessionMetaManager
from models import SessionMeta
from models.session_chat import resolve_session_chat_table_name


class SessionMetaManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "session_meta.sqlite"
        self.manager = SessionMetaManager(database_path=self.db_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.temp_dir.cleanup()

    def _build_session_meta(self, name: str = "session-a") -> SessionMeta:
        return SessionMeta(
            name=name,
            participants=[1, 2],
        )

    def test_auto_creates_session_meta_table(self) -> None:
        self.assertTrue(self.db_path.exists())

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()

        self.assertIn("sessionmeta", tables)

    def test_add_session_meta_populates_primary_key_and_chatid(self) -> None:
        session_meta = self._build_session_meta()

        self.manager.add_session_meta(session_meta)

        self.assertIsNotNone(session_meta.sid)
        self.assertIsNotNone(session_meta.created_time)
        self.assertIsNotNone(session_meta.updated_time)
        self.assertRegex(session_meta.chatid, r"^[0-9a-f]{32}$")

    def test_add_session_meta_auto_creates_corresponding_session_chat_table(self) -> None:
        session_meta = self._build_session_meta()

        self.manager.add_session_meta(session_meta)

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()

        self.assertIn(resolve_session_chat_table_name(session_meta.chatid), tables)

    def test_get_session_meta_returns_inserted_record(self) -> None:
        session_meta = self._build_session_meta()
        self.manager.add_session_meta(session_meta)

        saved_session_meta = self.manager.get_session_meta(session_meta.sid)

        self.assertIsNotNone(saved_session_meta)
        assert saved_session_meta is not None
        self.assertEqual(saved_session_meta.name, "session-a")
        self.assertEqual(saved_session_meta.chatid, session_meta.chatid)
        self.assertEqual(saved_session_meta.participants, [1, 2])

    def test_get_session_meta_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.get_session_meta(9999))

    def test_add_session_meta_defaults_participants_to_empty_list(self) -> None:
        session_meta = SessionMeta(name=None)

        self.manager.add_session_meta(session_meta)
        saved_session_meta = self.manager.get_session_meta(session_meta.sid)

        self.assertIsNotNone(saved_session_meta)
        assert saved_session_meta is not None
        self.assertEqual(saved_session_meta.participants, [])
        self.assertIsNone(saved_session_meta.name)

    def test_list_session_meta_returns_all_records_in_sid_order(self) -> None:
        first = self._build_session_meta(name="session-a")
        second = SessionMeta(
            name="session-b",
            participants=[3, 4, 5],
        )

        self.manager.add_session_meta(first)
        self.manager.add_session_meta(second)

        session_meta_list = self.manager.list_session_meta()

        self.assertEqual([item.name for item in session_meta_list], ["session-a", "session-b"])
        self.assertEqual([item.sid for item in session_meta_list], [first.sid, second.sid])
        self.assertNotEqual(first.chatid, second.chatid)

    def test_edit_session_meta_updates_fields_without_changing_chatid(self) -> None:
        session_meta = self._build_session_meta()
        self.manager.add_session_meta(session_meta)
        original_created_time = session_meta.created_time
        original_updated_time = session_meta.updated_time
        original_chatid = session_meta.chatid

        updated_session_meta = SessionMeta(
            name="session-a-updated",
            participants=[8, 9],
        )

        self.manager.edit_session_meta(session_meta.sid, updated_session_meta)
        saved_session_meta = self.manager.get_session_meta(session_meta.sid)

        self.assertIsNotNone(saved_session_meta)
        assert saved_session_meta is not None
        self.assertEqual(saved_session_meta.name, "session-a-updated")
        self.assertEqual(saved_session_meta.chatid, original_chatid)
        self.assertEqual(saved_session_meta.participants, [8, 9])
        self.assertEqual(saved_session_meta.created_time, original_created_time)
        self.assertGreaterEqual(saved_session_meta.updated_time, original_updated_time)

    def test_edit_session_meta_raises_when_missing(self) -> None:
        updated_session_meta = SessionMeta(
            name="ghost-session",
            participants=[0],
        )

        with self.assertRaises(ValueError):
            self.manager.edit_session_meta(404, updated_session_meta)

    def test_multiple_session_meta_records_generate_unique_chatids(self) -> None:
        first = self._build_session_meta(name="session-1")
        second = self._build_session_meta(name="session-2")
        third = self._build_session_meta(name="session-3")

        self.manager.add_session_meta(first)
        self.manager.add_session_meta(second)
        self.manager.add_session_meta(third)

        self.assertEqual(len({first.chatid, second.chatid, third.chatid}), 3)

    def test_delete_session_meta_removes_record_and_drops_chat_table(self) -> None:
        session_meta = self._build_session_meta()
        self.manager.add_session_meta(session_meta)
        session_chat_table_name = resolve_session_chat_table_name(session_meta.chatid)

        self.manager.delete_session_meta(session_meta.sid)

        self.assertIsNone(self.manager.get_session_meta(session_meta.sid))
        self.assertEqual(self.manager.list_session_meta(), [])

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()

        self.assertNotIn(session_chat_table_name, tables)

    def test_delete_session_meta_missing_is_no_op(self) -> None:
        self.manager.delete_session_meta(404)
        self.assertEqual(self.manager.list_session_meta(), [])

    def test_delete_session_meta_keeps_metadata_when_drop_fails(self) -> None:
        session_meta = self._build_session_meta()
        self.manager.add_session_meta(session_meta)

        with patch("core.session_meta.get_session_chat_table") as mock_get_table:
            mock_table = mock_get_table.return_value
            mock_table.drop.side_effect = RuntimeError("drop failed")

            with self.assertRaises(RuntimeError):
                self.manager.delete_session_meta(session_meta.sid)

        saved_session_meta = self.manager.get_session_meta(session_meta.sid)
        self.assertIsNotNone(saved_session_meta)


if __name__ == "__main__":
    unittest.main()
