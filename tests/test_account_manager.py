import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.exc import IntegrityError

from core import AccountManager, CustomerManager, PlatformManager
from models import Account, Customer, Platform


class AccountManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "account.sqlite"
        self.manager = AccountManager(database_path=self.db_path)
        self.customer_manager = CustomerManager(database_path=self.db_path)
        self.platform_manager = PlatformManager(database_path=self.db_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.customer_manager.engine.dispose()
        self.platform_manager.engine.dispose()
        self.temp_dir.cleanup()

    def _add_customer(self, name: str = "Alice") -> Customer:
        customer = Customer(name=name)
        self.customer_manager.add_customer(customer)
        return customer

    def _add_platform(self, pid: str = "wechat", name: str = "WeChat") -> Platform:
        platform = Platform(pid=pid, name=name)
        self.platform_manager.add_platform(platform)
        return platform

    def _build_account(self, account: str = "alice@example.com") -> Account:
        customer = self._add_customer()
        platform = self._add_platform()
        return Account(
            cid=customer.cid,
            pid=platform.pid,
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
        customer = self._add_customer(name="Test User")
        platform = self._add_platform(pid="wechat-test", name="WeChat Test")
        test_account = Account(
            cid=customer.cid,
            pid=platform.pid,
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
        self.assertEqual(saved_account.cid, customer.cid)
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

    def test_add_account_accepts_nullable_identity_fields(self) -> None:
        account = Account(
            cid=None,
            pid=None,
            account=None,
            nickname=None,
            avatar=None,
            sids=None,
            extra=None,
        )

        self.manager.add_account(account)
        saved_account = self.manager.get_account(account.aid)

        self.assertIsNotNone(saved_account)
        assert saved_account is not None
        self.assertIsNone(saved_account.cid)
        self.assertIsNone(saved_account.pid)
        self.assertIsNone(saved_account.account)
        self.assertIsNone(saved_account.nickname)
        self.assertIsNone(saved_account.avatar)

    def test_add_account_enforces_customer_and_platform_foreign_keys(self) -> None:
        account = Account(
            cid=9999,
            pid="missing-platform",
            account="ghost@example.com",
            nickname="Ghost",
            avatar="ghost.png",
            sids=[1],
            extra={"level": 0},
        )

        with self.assertRaises(IntegrityError):
            self.manager.add_account(account)

    def test_list_account_returns_all_accounts_in_aid_order(self) -> None:
        first = self._build_account(account="alice@example.com")
        second_customer = self._add_customer(name="Bella")
        second_platform = self._add_platform(pid="douyin", name="Douyin")
        second = Account(
            cid=second_customer.cid,
            pid=second_platform.pid,
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

        updated_customer = self._add_customer(name="Alice Zhang")
        updated_platform = self._add_platform(pid="wechat-updated", name="WeChat Updated")
        updated_account = Account(
            cid=updated_customer.cid,
            pid=updated_platform.pid,
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
        self.assertEqual(saved_account.cid, updated_customer.cid)
        self.assertEqual(saved_account.pid, "wechat-updated")
        self.assertEqual(saved_account.account, "alice-updated@example.com")
        self.assertEqual(saved_account.nickname, "Alice Zhang")
        self.assertEqual(saved_account.avatar, "updated.png")
        self.assertEqual(saved_account.sids, [8, 9])
        self.assertEqual(saved_account.extra, {"level": 5})
        self.assertEqual(saved_account.created_time, original_created_time)
        self.assertGreaterEqual(saved_account.updated_time, original_updated_time)

    def test_edit_account_raises_when_missing(self) -> None:
        customer = self._add_customer(name="Ghost")
        platform = self._add_platform(pid="ghost-platform", name="Ghost Platform")
        updated_account = Account(
            cid=customer.cid,
            pid=platform.pid,
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
