import sqlite3
import unittest
from datetime import timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from core import MetaManager
from models import Meta
from utils import utc_now


class MetaManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "meta.sqlite"
        self.manager = MetaManager(database_path=self.db_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.temp_dir.cleanup()

    def _count_rows(self) -> int:
        connection = sqlite3.connect(self.db_path)
        try:
            row = connection.execute("SELECT COUNT(*) FROM meta").fetchone()
            assert row is not None
            return int(row[0])
        finally:
            connection.close()

    def test_auto_creates_meta_table(self) -> None:
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

        self.assertIn("meta", tables)

    def test_get_version_returns_default_when_row_missing(self) -> None:
        version = self.manager.get_version()

        self.assertEqual(version, "1.0.0")
        self.assertEqual(self._count_rows(), 1)

    def test_update_version_persists_new_value(self) -> None:
        self.manager.update_version("1.2.3")

        self.assertEqual(self.manager.get_version(), "1.2.3")

    def test_update_version_creates_singleton_row_when_missing(self) -> None:
        self.manager.update_version("2.0.0")

        self.assertEqual(self.manager.get_version(), "2.0.0")
        self.assertEqual(self._count_rows(), 1)

    def test_repeated_updates_keep_singleton_row(self) -> None:
        self.manager.get_version()
        self.manager.update_version("1.0.1")
        self.manager.update_version("1.0.2")

        self.assertEqual(self.manager.get_version(), "1.0.2")
        self.assertEqual(self._count_rows(), 1)

    def test_model_is_exported(self) -> None:
        meta = Meta()

        self.assertEqual(meta.key, "version")
        self.assertEqual(meta.value, "1.0.0")

    def test_utils_utc_now_returns_timezone_aware_utc_datetime(self) -> None:
        current = utc_now()

        self.assertEqual(current.tzinfo, timezone.utc)
        self.assertEqual(current.utcoffset(), timezone.utc.utcoffset(current))


if __name__ == "__main__":
    unittest.main()
