import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import VersionManager
from models import Version


class VersionManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.config_path = self.temp_path / "sql.yml"
        self.db_path = self.temp_path / "version.sqlite"
        self.config_path.write_text("type: sqlite\npath: ./version.sqlite\n", encoding="utf-8")
        self.manager = VersionManager(config_path=self.config_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.temp_dir.cleanup()

    def _count_rows(self) -> int:
        connection = sqlite3.connect(self.db_path)
        try:
            row = connection.execute("SELECT COUNT(*) FROM version").fetchone()
            assert row is not None
            return int(row[0])
        finally:
            connection.close()

    def test_auto_creates_version_table(self) -> None:
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

        self.assertIn("version", tables)

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
        version = Version()

        self.assertEqual(version.key, "version")
        self.assertEqual(version.value, "1.0.0")


if __name__ == "__main__":
    unittest.main()
