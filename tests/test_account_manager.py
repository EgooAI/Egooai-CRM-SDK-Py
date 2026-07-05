import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import AccountManager
from models import Account


class AccountManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.config_path = self.temp_path / "sql.yml"
        self.db_path = self.temp_path / "account.sqlite"
        self.config_path.write_text("type: sqlite\npath: ./account.sqlite\n", encoding="utf-8")
        self.manager = AccountManager(config_path=self.config_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.temp_dir.cleanup()

    def _build_account(self, account: str = "alice@example.com") -> Account:
        return Account(
            cid=1,
            pid="wechat",
            account=account,
            nickname="Alice",
            avatar="alice.png",
            sids=[1, 2],
            extra={"level": 1},
        )

    def test_auto_creates_account_table(self) -> None:
        self.assertTrue(self.db_path.exists())

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

        self.assertIn("account", tables)

    def test_add_account_populates_primary_key(self) -> None:
        account = self._build_account()

        self.manager.add_account(account)

        self.assertIsNotNone(account.aid)
        self.assertIsNotNone(account.created_time)
        self.assertIsNotNone(account.updated_time)

    def test_add_account_test_data(self) -> None:
        test_account = Account(
            cid=1001,
            pid="wechat-test",
            account="test.user@egooai.com",
            nickname="Test User",
            avatar="test-user.png",
            sids=[100, 200, 300],
            extra={"source": "test", "status": "active"},
        )

        self.manager.add_account(test_account)
        saved_account = self.manager.get_account(test_account.aid)

        self.assertIsNotNone(saved_account)
        assert saved_account is not None
        self.assertEqual(saved_account.cid, 1001)
        self.assertEqual(saved_account.pid, "wechat-test")
        self.assertEqual(saved_account.account, "test.user@egooai.com")
        self.assertEqual(saved_account.nickname, "Test User")
        self.assertEqual(saved_account.avatar, "test-user.png")
        self.assertEqual(saved_account.sids, [100, 200, 300])
        self.assertEqual(saved_account.extra, {"source": "test", "status": "active"})

    def test_get_account_returns_inserted_account(self) -> None:
        account = self._build_account()
        self.manager.add_account(account)

        saved_account = self.manager.get_account(account.aid)

        self.assertIsNotNone(saved_account)
        assert saved_account is not None
        self.assertEqual(saved_account.account, "alice@example.com")
        self.assertEqual(saved_account.nickname, "Alice")
        self.assertEqual(saved_account.sids, [1, 2])
        self.assertEqual(saved_account.extra, {"level": 1})

    def test_get_account_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.get_account(9999))

    def test_list_account_returns_all_accounts_in_aid_order(self) -> None:
        first = self._build_account(account="alice@example.com")
        second = Account(
            cid=2,
            pid="douyin",
            account="bella@example.com",
            nickname="Bella",
            avatar="bella.png",
            sids=[3, 4],
            extra={"level": 2},
        )

        self.manager.add_account(first)
        self.manager.add_account(second)

        accounts = self.manager.list_account()

        self.assertEqual([account.account for account in accounts], ["alice@example.com", "bella@example.com"])
        self.assertEqual([account.aid for account in accounts], [first.aid, second.aid])

    def test_edit_account_updates_account_fields(self) -> None:
        account = self._build_account()
        self.manager.add_account(account)
        original_created_time = account.created_time
        original_updated_time = account.updated_time

        updated_account = Account(
            cid=10,
            pid="wechat-updated",
            account="alice-updated@example.com",
            nickname="Alice Zhang",
            avatar="updated.png",
            sids=[8, 9],
            extra={"level": 5},
        )

        self.manager.edit_account(account.aid, updated_account)
        saved_account = self.manager.get_account(account.aid)

        self.assertIsNotNone(saved_account)
        assert saved_account is not None
        self.assertEqual(saved_account.cid, 10)
        self.assertEqual(saved_account.pid, "wechat-updated")
        self.assertEqual(saved_account.account, "alice-updated@example.com")
        self.assertEqual(saved_account.nickname, "Alice Zhang")
        self.assertEqual(saved_account.avatar, "updated.png")
        self.assertEqual(saved_account.sids, [8, 9])
        self.assertEqual(saved_account.extra, {"level": 5})
        self.assertEqual(saved_account.created_time, original_created_time)
        self.assertGreaterEqual(saved_account.updated_time, original_updated_time)

    def test_edit_account_raises_when_missing(self) -> None:
        updated_account = Account(
            cid=1,
            pid="wechat",
            account="ghost@example.com",
            nickname="Ghost",
            avatar="ghost.png",
            sids=[0],
            extra={"level": 0},
        )

        with self.assertRaises(ValueError):
            self.manager.edit_account(404, updated_account)

    def test_delete_account_removes_record(self) -> None:
        account = self._build_account()
        self.manager.add_account(account)

        self.manager.delete_account(account.aid)

        self.assertIsNone(self.manager.get_account(account.aid))
        self.assertEqual(self.manager.list_account(), [])

    def test_delete_account_missing_is_no_op(self) -> None:
        self.manager.delete_account(404)
        self.assertEqual(self.manager.list_account(), [])


if __name__ == "__main__":
    unittest.main()
