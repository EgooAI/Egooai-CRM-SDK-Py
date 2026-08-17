import sqlite3
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import MetaManager
from models import Meta


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
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
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

    def test_upsert_meta_inserts_when_key_missing(self) -> None:
        meta = Meta(key="build", value="42")

        self.manager.upsert_meta(meta)

        self.assertEqual(meta.key, "build")
        self.assertEqual(self._count_rows(), 1)

    def test_upsert_meta_updates_existing_key_without_creating_duplicate(self) -> None:
        first = Meta(key="build", value="42")
        self.manager.upsert_meta(first)
        second = Meta(key="build", value="43")

        self.manager.upsert_meta(second)

        self.assertEqual(self._count_rows(), 1)
        connection = sqlite3.connect(self.db_path)
        try:
            row = connection.execute("SELECT value FROM meta WHERE key = 'build'").fetchone()
        finally:
            connection.close()
        assert row is not None
        self.assertEqual(row[0], "43")

    def test_upsert_meta_skips_duplicate_value(self) -> None:
        meta = Meta(key="build", value="42")
        self.manager.upsert_meta(meta)
        duplicate_meta = Meta(key="build", value="42")

        self.manager.upsert_meta(duplicate_meta)

        self.assertEqual(self._count_rows(), 1)
        self.assertEqual(duplicate_meta.key, "build")
        self.assertEqual(duplicate_meta.value, "42")

    def test_concurrent_get_version_creates_singleton_row_once(self) -> None:
        results: list[str] = []
        errors: list[BaseException] = []

        def _worker() -> None:
            try:
                results.append(self.manager.get_version())
            except BaseException as exc:  # pragma: no cover - test captures thread failures
                errors.append(exc)

        threads = [threading.Thread(target=_worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(results, ["1.0.0", "1.0.0"])
        self.assertEqual(self._count_rows(), 1)


if __name__ == "__main__":
    unittest.main()
