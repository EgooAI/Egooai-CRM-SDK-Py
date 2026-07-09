import sqlite3
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.exc import IntegrityError

from core import AccountManager, AccountMappingManager, CustomerManager, PlatformManager
from models import Account, AccountMapping, Customer, Platform


class AccountMappingManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "account_mapping.sqlite"
        self.manager = AccountMappingManager(database_path=self.db_path)
        self.account_manager = AccountManager(database_path=self.db_path)
        self.customer_manager = CustomerManager(database_path=self.db_path)
        self.platform_manager = PlatformManager(database_path=self.db_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.account_manager.engine.dispose()
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

    def _build_account_mapping(
        self,
        aid: int,
        type_: str | None = "openid",
        key: str | None = "wx-open-id",
    ) -> AccountMapping:
        return AccountMapping(aid=aid, type=type_, key=key)

    def test_managers_share_database_lock_for_same_path(self) -> None:
        self.assertIs(self.manager._lock, self.account_manager._lock)
        self.assertIs(self.manager._lock, self.customer_manager._lock)
        self.assertIs(self.manager._lock, self.platform_manager._lock)

    def test_auto_creates_account_mapping_table(self) -> None:
        self.assertTrue(self.db_path.exists())

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()

        self.assertIn("accountmapping", tables)

    def test_add_account_mapping_populates_primary_key(self) -> None:
        account = self._add_account()
        account_mapping = self._build_account_mapping(account.aid)

        self.manager.add_account_mapping(account_mapping)

        self.assertIsNotNone(account_mapping.amid)

    def test_get_account_mapping_returns_inserted_mapping(self) -> None:
        account = self._add_account()
        account_mapping = self._build_account_mapping(account.aid)
        self.manager.add_account_mapping(account_mapping)

        saved_account_mapping = self.manager.get_account_mapping(account_mapping.amid)

        self.assertIsNotNone(saved_account_mapping)
        assert saved_account_mapping is not None
        self.assertEqual(saved_account_mapping.aid, account.aid)
        self.assertEqual(saved_account_mapping.type, "openid")
        self.assertEqual(saved_account_mapping.key, "wx-open-id")

    def test_get_account_mapping_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.get_account_mapping(9999))

    def test_add_account_mapping_accepts_nullable_type_and_key(self) -> None:
        account = self._add_account()
        account_mapping = AccountMapping(aid=account.aid, type=None, key=None)

        self.manager.add_account_mapping(account_mapping)
        saved_account_mapping = self.manager.get_account_mapping(account_mapping.amid)

        self.assertIsNotNone(saved_account_mapping)
        assert saved_account_mapping is not None
        self.assertIsNone(saved_account_mapping.type)
        self.assertIsNone(saved_account_mapping.key)

    def test_add_account_mapping_requires_non_null_aid(self) -> None:
        account_mapping = AccountMapping(aid=None, type="openid", key="wx-open-id")

        with self.assertRaises(IntegrityError):
            self.manager.add_account_mapping(account_mapping)

    def test_add_account_mapping_enforces_account_foreign_key(self) -> None:
        account_mapping = self._build_account_mapping(9999)

        with self.assertRaises(IntegrityError):
            self.manager.add_account_mapping(account_mapping)

    def test_list_account_mapping_returns_all_mappings_in_amid_order(self) -> None:
        first_account = self._add_account("alice@example.com")
        second_account = self._add_account(
            "bella@example.com",
            customer_name="Bella",
            pid="douyin",
            platform_name="Douyin",
        )
        first = self._build_account_mapping(first_account.aid, type_="openid", key="alice-openid")
        second = self._build_account_mapping(second_account.aid, type_="unionid", key="bella-unionid")

        self.manager.add_account_mapping(first)
        self.manager.add_account_mapping(second)

        account_mappings = self.manager.list_account_mapping()

        self.assertEqual([mapping.amid for mapping in account_mappings], [first.amid, second.amid])
        self.assertEqual([mapping.type for mapping in account_mappings], ["openid", "unionid"])

    def test_edit_account_mapping_updates_fields(self) -> None:
        first_account = self._add_account("alice@example.com")
        second_account = self._add_account(
            "bella@example.com",
            customer_name="Bella",
            pid="douyin",
            platform_name="Douyin",
        )
        account_mapping = self._build_account_mapping(first_account.aid)
        self.manager.add_account_mapping(account_mapping)

        updated_account_mapping = AccountMapping(
            aid=second_account.aid,
            type="unionid",
            key="bella-unionid",
        )

        self.manager.edit_account_mapping(account_mapping.amid, updated_account_mapping)
        saved_account_mapping = self.manager.get_account_mapping(account_mapping.amid)

        self.assertIsNotNone(saved_account_mapping)
        assert saved_account_mapping is not None
        self.assertEqual(saved_account_mapping.aid, second_account.aid)
        self.assertEqual(saved_account_mapping.type, "unionid")
        self.assertEqual(saved_account_mapping.key, "bella-unionid")

    def test_edit_account_mapping_raises_when_missing(self) -> None:
        account = self._add_account()
        updated_account_mapping = self._build_account_mapping(account.aid)

        with self.assertRaises(ValueError):
            self.manager.edit_account_mapping(404, updated_account_mapping)

    def test_delete_account_mapping_removes_record(self) -> None:
        account = self._add_account()
        account_mapping = self._build_account_mapping(account.aid)
        self.manager.add_account_mapping(account_mapping)

        self.manager.delete_account_mapping(account_mapping.amid)

        self.assertIsNone(self.manager.get_account_mapping(account_mapping.amid))
        self.assertEqual(self.manager.list_account_mapping(), [])

    def test_delete_account_mapping_missing_is_no_op(self) -> None:
        self.manager.delete_account_mapping(404)
        self.assertEqual(self.manager.list_account_mapping(), [])

    def test_upsert_account_mapping_inserts_when_missing(self) -> None:
        account = self._add_account()
        account_mapping = self._build_account_mapping(account.aid)

        self.manager.upsert_account_mapping(account_mapping)

        self.assertIsNotNone(account_mapping.amid)
        self.assertEqual(len(self.manager.list_account_mapping()), 1)

    def test_upsert_account_mapping_updates_existing_fields(self) -> None:
        first_account = self._add_account("alice@example.com")
        second_account = self._add_account(
            "bella@example.com",
            customer_name="Bella",
            pid="douyin",
            platform_name="Douyin",
        )
        account_mapping = self._build_account_mapping(first_account.aid)
        self.manager.add_account_mapping(account_mapping)

        updated_account_mapping = AccountMapping(
            amid=account_mapping.amid,
            aid=second_account.aid,
            type="unionid",
            key="bella-unionid",
        )

        self.manager.upsert_account_mapping(updated_account_mapping)
        saved_account_mapping = self.manager.get_account_mapping(account_mapping.amid)

        self.assertIsNotNone(saved_account_mapping)
        assert saved_account_mapping is not None
        self.assertEqual(saved_account_mapping.aid, second_account.aid)
        self.assertEqual(saved_account_mapping.type, "unionid")
        self.assertEqual(saved_account_mapping.key, "bella-unionid")

    def test_upsert_account_mapping_skips_duplicate_payload_without_primary_key(self) -> None:
        account = self._add_account()
        account_mapping = self._build_account_mapping(account.aid)
        self.manager.add_account_mapping(account_mapping)
        duplicate_account_mapping = self._build_account_mapping(account.aid)

        self.manager.upsert_account_mapping(duplicate_account_mapping)

        self.assertEqual(len(self.manager.list_account_mapping()), 1)
        self.assertEqual(duplicate_account_mapping.amid, account_mapping.amid)

    def test_upsert_account_mapping_raises_when_explicit_primary_key_missing(self) -> None:
        account = self._add_account()
        missing_account_mapping = AccountMapping(amid=999, aid=account.aid, type="openid", key="missing")

        with self.assertRaises(ValueError):
            self.manager.upsert_account_mapping(missing_account_mapping)

    def test_upsert_account_mapping_enforces_account_foreign_key(self) -> None:
        account_mapping = self._build_account_mapping(9999)

        with self.assertRaises(IntegrityError):
            self.manager.upsert_account_mapping(account_mapping)

    def test_concurrent_upsert_account_mapping_skips_duplicate_payload(self) -> None:
        account = self._add_account()
        errors: list[BaseException] = []

        def _worker() -> None:
            try:
                self.manager.upsert_account_mapping(AccountMapping(aid=account.aid, type="openid", key="wx-open-id"))
            except BaseException as exc:  # pragma: no cover - test captures thread failures
                errors.append(exc)

        threads = [threading.Thread(target=_worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(self.manager.list_account_mapping()), 1)


if __name__ == "__main__":
    unittest.main()
