import sqlite3
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from core import CustomerManager, bootstrap_engine
from models import Customer
from utils import utc_now


class CustomerManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "customer.sqlite"
        self.manager = CustomerManager(database_path=self.db_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.temp_dir.cleanup()

    def _build_customer(self, name: str = "Alice") -> Customer:
        return Customer(
            name=name,
            sex="F",
            birthdate=date(1995, 5, 1),
            region="Shanghai",
            extra={"level": 1},
            image={"avatar": f"{name.lower()}.png"},
        )

    def test_auto_creates_customer_table(self) -> None:
        self.assertTrue(self.db_path.exists())

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()

        self.assertIn("customer", tables)

    def test_add_customer_populates_primary_key(self) -> None:
        customer = self._build_customer()

        self.manager.add_customer(customer)

        self.assertIsNotNone(customer.cid)
        self.assertIsNotNone(customer.created_time)
        self.assertIsNotNone(customer.updated_time)

    def test_get_customer_returns_inserted_customer(self) -> None:
        customer = self._build_customer()
        self.manager.add_customer(customer)

        saved_customer = self.manager.get_customer(customer.cid)

        self.assertIsNotNone(saved_customer)
        assert saved_customer is not None
        self.assertEqual(saved_customer.name, "Alice")
        self.assertEqual(saved_customer.extra, {"level": 1})
        self.assertEqual(saved_customer.image, {"avatar": "alice.png"})

    def test_get_customer_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.get_customer(9999))

    def test_add_customer_accepts_nullable_profile_fields(self) -> None:
        customer = Customer(name=None, sex=None, birthdate=None, region=None)

        self.manager.add_customer(customer)
        saved_customer = self.manager.get_customer(customer.cid)

        self.assertIsNotNone(saved_customer)
        assert saved_customer is not None
        self.assertIsNone(saved_customer.name)
        self.assertIsNone(saved_customer.sex)
        self.assertIsNone(saved_customer.birthdate)
        self.assertIsNone(saved_customer.region)

    def test_list_customer_returns_all_customers_in_cid_order(self) -> None:
        first = self._build_customer(name="Alice")
        second = self._build_customer(name="Bella")

        self.manager.add_customer(first)
        self.manager.add_customer(second)

        customers = self.manager.list_customer()

        self.assertEqual([customer.name for customer in customers], ["Alice", "Bella"])
        self.assertEqual([customer.cid for customer in customers], [first.cid, second.cid])

    def test_edit_customer_updates_customer_fields(self) -> None:
        customer = self._build_customer()
        self.manager.add_customer(customer)
        original_created_time = customer.created_time
        original_updated_time = customer.updated_time

        updated_customer = Customer(
            name="Alice Zhang",
            sex="F",
            birthdate=date(1995, 5, 1),
            region="Beijing",
            extra={"level": 2},
            image={"avatar": "updated.png"},
        )

        self.manager.edit_customer(customer.cid, updated_customer)
        saved_customer = self.manager.get_customer(customer.cid)

        self.assertIsNotNone(saved_customer)
        assert saved_customer is not None
        self.assertEqual(saved_customer.name, "Alice Zhang")
        self.assertEqual(saved_customer.region, "Beijing")
        self.assertEqual(saved_customer.extra, {"level": 2})
        self.assertEqual(saved_customer.image, {"avatar": "updated.png"})
        self.assertEqual(saved_customer.created_time, original_created_time)
        self.assertGreaterEqual(saved_customer.updated_time, original_updated_time)

    def test_edit_customer_raises_when_missing(self) -> None:
        updated_customer = Customer(
            name="Ghost",
            sex="M",
            birthdate=date(2000, 1, 1),
            region="Nowhere",
            extra={"level": 0},
            image={"avatar": "ghost.png"},
        )

        with self.assertRaises(ValueError):
            self.manager.edit_customer(404, updated_customer)

    def test_delete_customer_removes_record(self) -> None:
        customer = self._build_customer()
        self.manager.add_customer(customer)

        self.manager.delete_customer(customer.cid)

        self.assertIsNone(self.manager.get_customer(customer.cid))
        self.assertEqual(self.manager.list_customer(), [])

    def test_delete_customer_missing_is_no_op(self) -> None:
        self.manager.delete_customer(404)
        self.assertEqual(self.manager.list_customer(), [])

    def test_bootstrap_engine_creates_database_file_for_explicit_path(self) -> None:
        database_path, engine = bootstrap_engine(self.db_path)
        try:
            self.assertEqual(database_path, self.db_path.resolve())
            self.assertTrue(database_path.exists())
        finally:
            engine.dispose()

    def test_bootstrap_engine_resolves_relative_database_path(self) -> None:
        relative_path = Path("tests-temp") / "nested" / "customer.sqlite"

        database_path, engine = bootstrap_engine(relative_path)
        try:
            self.assertEqual(database_path, relative_path.resolve())
            self.assertTrue(database_path.exists())
        finally:
            engine.dispose()
            if database_path.exists():
                database_path.unlink()
            parent = database_path.parent
            while parent.name != "Egooai-CRM-SDK-Py" and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent

    def test_utils_utc_now_is_timezone_aware(self) -> None:
        current = utc_now()

        self.assertIsNotNone(current.tzinfo)


if __name__ == "__main__":
    unittest.main()
