import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import SessionChatManager, SessionMetaManager
from models import SessionChat, SessionMeta
from models.SessionChat import resolve_session_chat_table_name


class SessionChatManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.config_path = self.temp_path / "sql.yml"
        self.db_path = self.temp_path / "session_chat.sqlite"
        self.config_path.write_text("type: sqlite\npath: ./session_chat.sqlite\n", encoding="utf-8")
        self.manager = SessionChatManager(config_path=self.config_path)
        self.session_meta_manager = SessionMetaManager(config_path=self.config_path)
        self.alpha_chatid = "0123456789abcdef0123456789abcdef"
        self.beta_chatid = "fedcba9876543210fedcba9876543210"

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.session_meta_manager.engine.dispose()
        self.temp_dir.cleanup()

    def _build_session_chat(self, sender: int = 1001, type_: str = "text") -> SessionChat:
        return SessionChat(
            sender=sender,
            type=type_,
            content={"text": "hello"},
            read=None,
        )

    def _build_session_meta(self, name: str = "session-a") -> SessionMeta:
        return SessionMeta(
            name=name,
            participants=[1, 2],
        )

    def test_add_session_chat_auto_creates_target_table(self) -> None:
        chat = self._build_session_chat()

        self.manager.add_session_chat(self.alpha_chatid, chat)

        self.assertIsNotNone(chat.id)
        self.assertIsNotNone(chat.created_time)
        self.assertIsNotNone(chat.updated_time)

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            connection.close()

        self.assertIn(resolve_session_chat_table_name(self.alpha_chatid), tables)

    def test_get_session_chat_returns_inserted_record(self) -> None:
        chat = self._build_session_chat()
        self.manager.add_session_chat(self.alpha_chatid, chat)

        saved_chat = self.manager.get_session_chat(self.alpha_chatid, chat.id)

        self.assertIsNotNone(saved_chat)
        assert saved_chat is not None
        self.assertEqual(saved_chat.sender, 1001)
        self.assertEqual(saved_chat.type, "text")
        self.assertEqual(saved_chat.content, {"text": "hello"})
        self.assertIsNone(saved_chat.read)

    def test_get_session_chat_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.get_session_chat(self.alpha_chatid, 9999))

    def test_list_session_chat_returns_all_records_in_id_order(self) -> None:
        first = self._build_session_chat(sender=1, type_="text")
        second = SessionChat(
            sender=2,
            type="image",
            content={"url": "cover.png"},
            read=False,
        )

        self.manager.add_session_chat(self.alpha_chatid, first)
        self.manager.add_session_chat(self.alpha_chatid, second)

        chats = self.manager.list_session_chat(self.alpha_chatid)

        self.assertEqual([chat.id for chat in chats], [first.id, second.id])
        self.assertEqual([chat.type for chat in chats], ["text", "image"])

    def test_edit_session_chat_updates_fields(self) -> None:
        chat = self._build_session_chat()
        self.manager.add_session_chat(self.alpha_chatid, chat)
        original_created_time = chat.created_time
        original_updated_time = chat.updated_time

        updated_chat = SessionChat(
            sender=2002,
            type="card",
            content={"title": "updated"},
            read=True,
        )

        self.manager.edit_session_chat(self.alpha_chatid, chat.id, updated_chat)
        saved_chat = self.manager.get_session_chat(self.alpha_chatid, chat.id)

        self.assertIsNotNone(saved_chat)
        assert saved_chat is not None
        self.assertEqual(saved_chat.sender, 2002)
        self.assertEqual(saved_chat.type, "card")
        self.assertEqual(saved_chat.content, {"title": "updated"})
        self.assertTrue(saved_chat.read)
        self.assertEqual(saved_chat.created_time, original_created_time)
        self.assertGreaterEqual(saved_chat.updated_time, original_updated_time)

    def test_edit_session_chat_raises_when_missing(self) -> None:
        updated_chat = SessionChat(
            sender=1,
            type="text",
            content={"text": "ghost"},
            read=False,
        )

        with self.assertRaises(ValueError):
            self.manager.edit_session_chat(self.alpha_chatid, 404, updated_chat)

    def test_delete_session_chat_removes_record(self) -> None:
        chat = self._build_session_chat()
        self.manager.add_session_chat(self.alpha_chatid, chat)

        self.manager.delete_session_chat(self.alpha_chatid, chat.id)

        self.assertIsNone(self.manager.get_session_chat(self.alpha_chatid, chat.id))
        self.assertEqual(self.manager.list_session_chat(self.alpha_chatid), [])

    def test_delete_session_chat_missing_is_no_op(self) -> None:
        self.manager.delete_session_chat(self.alpha_chatid, 404)
        self.assertEqual(self.manager.list_session_chat(self.alpha_chatid), [])

    def test_different_chatids_keep_records_isolated(self) -> None:
        alpha_chat = self._build_session_chat(sender=1)
        beta_chat = SessionChat(
            sender=2,
            type="text",
            content={"text": "beta"},
            read=False,
        )

        self.manager.add_session_chat(self.alpha_chatid, alpha_chat)
        self.manager.add_session_chat(self.beta_chatid, beta_chat)

        alpha_chats = self.manager.list_session_chat(self.alpha_chatid)
        beta_chats = self.manager.list_session_chat(self.beta_chatid)

        self.assertEqual([chat.content for chat in alpha_chats], [{"text": "hello"}])
        self.assertEqual([chat.content for chat in beta_chats], [{"text": "beta"}])

    def test_ensure_session_chat_table_is_idempotent(self) -> None:
        first_name = self.manager.ensure_session_chat_table(self.alpha_chatid)
        second_name = self.manager.ensure_session_chat_table(self.alpha_chatid)

        self.assertEqual(first_name, second_name)
        self.assertEqual(first_name, f"sessionchat_{self.alpha_chatid}")

    def test_invalid_chatid_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.ensure_session_chat_table("sqlite_bad")

        with self.assertRaises(ValueError):
            self.manager.ensure_session_chat_table("bad-name")

        with self.assertRaises(ValueError):
            self.manager.ensure_session_chat_table("ABCDEF0123456789ABCDEF0123456789")

        with self.assertRaises(ValueError):
            self.manager.ensure_session_chat_table("123")

    def test_add_session_chat_by_sid_routes_to_session_chat_table(self) -> None:
        session_meta = self._build_session_meta()
        self.session_meta_manager.add_session_meta(session_meta)
        chat = self._build_session_chat()

        self.manager.add_session_chat_by_sid(session_meta.sid, chat)
        saved_chat = self.manager.get_session_chat(session_meta.chatid, chat.id)

        self.assertIsNotNone(saved_chat)
        assert saved_chat is not None
        self.assertEqual(saved_chat.content, {"text": "hello"})

    def test_list_session_chat_by_sid_returns_session_rows(self) -> None:
        session_meta = self._build_session_meta()
        self.session_meta_manager.add_session_meta(session_meta)
        first = self._build_session_chat(sender=1)
        second = SessionChat(
            sender=2,
            type="image",
            content={"url": "cover.png"},
            read=False,
        )

        self.manager.add_session_chat_by_sid(session_meta.sid, first)
        self.manager.add_session_chat_by_sid(session_meta.sid, second)

        chats = self.manager.list_session_chat_by_sid(session_meta.sid)

        self.assertEqual([chat.id for chat in chats], [first.id, second.id])
        self.assertEqual([chat.sender for chat in chats], [1, 2])

    def test_sid_based_methods_raise_when_session_missing(self) -> None:
        chat = self._build_session_chat()

        with self.assertRaises(ValueError):
            self.manager.add_session_chat_by_sid(404, chat)

        with self.assertRaises(ValueError):
            self.manager.get_session_chat_by_sid(404, 1)

        with self.assertRaises(ValueError):
            self.manager.list_session_chat_by_sid(404)

        with self.assertRaises(ValueError):
            self.manager.delete_session_chat_by_sid(404, 1)

        with self.assertRaises(ValueError):
            self.manager.edit_session_chat_by_sid(404, 1, chat)


if __name__ == "__main__":
    unittest.main()
