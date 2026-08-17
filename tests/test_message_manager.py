import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.exc import IntegrityError

from core import AccountManager, CustomerManager, MessageManager, PlatformManager, SessionMetaManager
from models import Account, Customer, Message, Platform, SessionMeta


class MessageManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "message.sqlite"
        self.manager = MessageManager(database_path=self.db_path)
        self.account_manager = AccountManager(database_path=self.db_path)
        self.customer_manager = CustomerManager(database_path=self.db_path)
        self.platform_manager = PlatformManager(database_path=self.db_path)
        self.session_meta_manager = SessionMetaManager(database_path=self.db_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.account_manager.engine.dispose()
        self.customer_manager.engine.dispose()
        self.platform_manager.engine.dispose()
        self.session_meta_manager.engine.dispose()
        self.temp_dir.cleanup()

    def _add_customer(self, name: str = "Alice") -> Customer:
        customer = Customer(name=name)
        self.customer_manager.add_customer(customer)
        return customer

    def _add_platform(self, pid: str = "wechat", name: str = "WeChat") -> Platform:
        platform = Platform(pid=pid, name=name)
        self.platform_manager.add_platform(platform)
        return platform

    def _add_account(
        self,
        account: str = "alice@example.com",
        customer_name: str = "Alice",
        pid: str = "wechat",
        platform_name: str = "WeChat",
    ) -> Account:
        customer = self._add_customer(name=customer_name)
        platform = self._add_platform(pid=pid, name=platform_name)
        account_record = Account(
            cid=customer.cid,
            pid=platform.pid,
            account=account,
            nickname="Alice",
            avatar="alice.png",
            sids=[1, 2],
            extra={"level": 1},
        )
        self.account_manager.add_account(account_record)
        return account_record

    def _add_session_meta(self, name: str = "session-a") -> SessionMeta:
        session_meta = SessionMeta(name=name, participants=[1, 2])
        self.session_meta_manager.add_session_meta(session_meta)
        return session_meta

    def _build_message(
        self,
        external_mid: str = "msg-001",
        sid: int = 1,
        sender: int = 1,
        created_at: datetime | None = None,
    ) -> Message:
        return Message(
            external_mid=external_mid,
            sid=sid,
            sender=sender,
            read=False,
            content={"text": "hello"},
            type="text",
            created_at=created_at,
        )

    def test_auto_creates_message_table(self) -> None:
        self.assertTrue(self.db_path.exists())

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()

        self.assertIn("message", tables)

    def test_add_message_persists_primary_key(self) -> None:
        account = self._add_account()
        session_meta = self._add_session_meta()
        message = self._build_message(sid=session_meta.sid, sender=account.aid)

        self.manager.add_message(message)

        self.assertEqual(message.external_mid, "msg-001")

    def test_get_message_returns_inserted_record(self) -> None:
        account = self._add_account()
        session_meta = self._add_session_meta()
        message = self._build_message(sid=session_meta.sid, sender=account.aid)
        self.manager.add_message(message)

        saved_message = self.manager.get_message(message.external_mid)

        self.assertIsNotNone(saved_message)
        assert saved_message is not None
        self.assertEqual(saved_message.sid, session_meta.sid)
        self.assertEqual(saved_message.sender, account.aid)
        self.assertFalse(saved_message.read)
        self.assertEqual(saved_message.content, {"text": "hello"})
        self.assertEqual(saved_message.type, "text")

    def test_message_persists_created_at(self) -> None:
        account = self._add_account()
        session_meta = self._add_session_meta()
        created_at = datetime(2026, 7, 1, 12, 30, 0, tzinfo=timezone.utc)
        message = self._build_message(
            sid=session_meta.sid,
            sender=account.aid,
            created_at=created_at,
        )

        self.manager.add_message(message)
        saved_message = self.manager.get_message(message.external_mid)

        self.assertIsNotNone(saved_message)
        assert saved_message is not None
        self.assertEqual(saved_message.created_at, created_at.replace(tzinfo=None))

    def test_get_message_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.get_message("missing-mid"))

    def test_add_message_allows_read_to_be_none(self) -> None:
        account = self._add_account()
        session_meta = self._add_session_meta()
        message = Message(
            external_mid="msg-null-read",
            sid=session_meta.sid,
            sender=account.aid,
            read=None,
            content={"text": "pending read state"},
            type="text",
        )

        self.manager.add_message(message)
        saved_message = self.manager.get_message(message.external_mid)

        self.assertIsNotNone(saved_message)
        assert saved_message is not None
        self.assertIsNone(saved_message.read)

    def test_add_message_enforces_session_meta_foreign_key(self) -> None:
        account = self._add_account()
        message = self._build_message(sid=9999, sender=account.aid)

        with self.assertRaises(IntegrityError):
            self.manager.add_message(message)

    def test_add_message_enforces_account_foreign_key(self) -> None:
        session_meta = self._add_session_meta()
        message = self._build_message(sid=session_meta.sid, sender=9999)

        with self.assertRaises(IntegrityError):
            self.manager.add_message(message)

    def test_list_message_returns_all_records_in_primary_key_order(self) -> None:
        first_account = self._add_account("alice@example.com")
        second_account = self._add_account(
            "bella@example.com",
            customer_name="Bella",
            pid="douyin",
            platform_name="Douyin",
        )
        first_session_meta = self._add_session_meta("session-a")
        second_session_meta = self._add_session_meta("session-b")
        first = self._build_message("msg-001", sid=first_session_meta.sid, sender=first_account.aid)
        second = Message(
            external_mid="msg-002",
            sid=second_session_meta.sid,
            sender=second_account.aid,
            read=True,
            content={"url": "cover.png"},
            type="image",
        )

        self.manager.add_message(first)
        self.manager.add_message(second)

        messages = self.manager.list_message()

        self.assertEqual([message.external_mid for message in messages], ["msg-001", "msg-002"])
        self.assertEqual([message.type for message in messages], ["text", "image"])

    def test_edit_message_updates_fields(self) -> None:
        first_account = self._add_account("alice@example.com")
        second_account = self._add_account(
            "bella@example.com",
            customer_name="Bella",
            pid="douyin",
            platform_name="Douyin",
        )
        first_session_meta = self._add_session_meta("session-a")
        second_session_meta = self._add_session_meta("session-b")
        message = self._build_message(sid=first_session_meta.sid, sender=first_account.aid)
        self.manager.add_message(message)

        updated_message = Message(
            external_mid="ignored-mid",
            sid=second_session_meta.sid,
            sender=second_account.aid,
            read=True,
            content={"text": "updated"},
            type="card",
        )

        self.manager.edit_message(message.external_mid, updated_message)
        saved_message = self.manager.get_message(message.external_mid)

        self.assertIsNotNone(saved_message)
        assert saved_message is not None
        self.assertEqual(saved_message.sid, second_session_meta.sid)
        self.assertEqual(saved_message.sender, second_account.aid)
        self.assertTrue(saved_message.read)
        self.assertEqual(saved_message.content, {"text": "updated"})
        self.assertEqual(saved_message.type, "card")

    def test_edit_message_raises_when_missing(self) -> None:
        account = self._add_account()
        session_meta = self._add_session_meta()
        updated_message = self._build_message(sid=session_meta.sid, sender=account.aid)

        with self.assertRaises(ValueError):
            self.manager.edit_message("missing-mid", updated_message)

    def test_delete_message_removes_record(self) -> None:
        account = self._add_account()
        session_meta = self._add_session_meta()
        message = self._build_message(sid=session_meta.sid, sender=account.aid)
        self.manager.add_message(message)

        self.manager.delete_message(message.external_mid)

        self.assertIsNone(self.manager.get_message(message.external_mid))
        self.assertEqual(self.manager.list_message(), [])

    def test_delete_message_missing_is_no_op(self) -> None:
        self.manager.delete_message("missing-mid")
        self.assertEqual(self.manager.list_message(), [])

    def test_upsert_message_inserts_when_missing(self) -> None:
        account = self._add_account()
        session_meta = self._add_session_meta()
        message = self._build_message(external_mid="msg-upsert", sid=session_meta.sid, sender=account.aid)

        self.manager.upsert_message(message)

        self.assertEqual(message.external_mid, "msg-upsert")
        self.assertEqual(len(self.manager.list_message()), 1)

    def test_upsert_message_updates_existing_fields(self) -> None:
        first_account = self._add_account("alice@example.com")
        second_account = self._add_account(
            "bella@example.com",
            customer_name="Bella",
            pid="douyin",
            platform_name="Douyin",
        )
        first_session_meta = self._add_session_meta("session-a")
        second_session_meta = self._add_session_meta("session-b")
        message = self._build_message(sid=first_session_meta.sid, sender=first_account.aid)
        self.manager.add_message(message)
        updated_message = Message(
            external_mid=message.external_mid,
            sid=second_session_meta.sid,
            sender=second_account.aid,
            read=True,
            content={"text": "updated"},
            type="card",
        )

        self.manager.upsert_message(updated_message)
        saved_message = self.manager.get_message(message.external_mid)

        self.assertIsNotNone(saved_message)
        assert saved_message is not None
        self.assertEqual(saved_message.sid, second_session_meta.sid)
        self.assertEqual(saved_message.sender, second_account.aid)
        self.assertTrue(saved_message.read)
        self.assertEqual(saved_message.content, {"text": "updated"})
        self.assertEqual(len(self.manager.list_message()), 1)

    def test_upsert_message_skips_duplicate_payload(self) -> None:
        account = self._add_account()
        session_meta = self._add_session_meta()
        message = self._build_message(sid=session_meta.sid, sender=account.aid)
        self.manager.add_message(message)
        duplicate_message = Message(
            external_mid=message.external_mid,
            sid=session_meta.sid,
            sender=account.aid,
            read=False,
            content={"text": "hello"},
            type="text",
        )

        self.manager.upsert_message(duplicate_message)

        self.assertEqual(len(self.manager.list_message()), 1)

    def test_upsert_message_enforces_foreign_keys(self) -> None:
        invalid_message = self._build_message(external_mid="msg-invalid", sid=9999, sender=9999)

        with self.assertRaises(IntegrityError):
            self.manager.upsert_message(invalid_message)


if __name__ == "__main__":
    unittest.main()
