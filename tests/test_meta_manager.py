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

    def test_get_version_returns_default_when_row_missing(self) -> None:
        version = self.manager.get_version()

        self.assertEqual(version, "1.0.0")
        self.assertEqual(self._count_rows(), 1)

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

    def test_upsert_meta_inserts_updates_and_deduplicates_key(self) -> None:
        for value in ("42", "43", "43"):
            with self.subTest(value=value):
                self.manager.upsert_meta(Meta(key="build", value=value))
                self.assertEqual(self._count_rows(), 1)
                connection = sqlite3.connect(self.db_path)
                try:
                    rows = connection.execute("SELECT key, value FROM meta").fetchall()
                finally:
                    connection.close()
                self.assertEqual(rows, [("build", value)])

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
