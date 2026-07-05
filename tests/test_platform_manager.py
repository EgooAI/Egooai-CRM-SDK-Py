import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import PlatformManager
from models import Platform


class PlatformManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.config_path = self.temp_path / "sql.yml"
        self.db_path = self.temp_path / "platform.sqlite"
        self.config_path.write_text("type: sqlite\npath: ./platform.sqlite\n", encoding="utf-8")
        self.manager = PlatformManager(config_path=self.config_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.temp_dir.cleanup()

    def _build_platform(self, pid: str = "wechat") -> Platform:
        return Platform(
            pid=pid,
            name="WeChat",
            extra={"region": "cn"},
        )

    def test_auto_creates_platform_table(self) -> None:
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

        self.assertIn("platform", tables)

    def test_add_platform_persists_record(self) -> None:
        platform = self._build_platform()

        self.manager.add_platform(platform)

        self.assertEqual(platform.pid, "wechat")
        self.assertIsNotNone(platform.created_time)
        self.assertIsNotNone(platform.updated_time)

    def test_get_platform_returns_inserted_platform(self) -> None:
        platform = self._build_platform()
        self.manager.add_platform(platform)

        saved_platform = self.manager.get_platform(platform.pid)

        self.assertIsNotNone(saved_platform)
        assert saved_platform is not None
        self.assertEqual(saved_platform.pid, "wechat")
        self.assertEqual(saved_platform.name, "WeChat")
        self.assertEqual(saved_platform.extra, {"region": "cn"})

    def test_get_platform_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.get_platform("missing"))

    def test_list_platform_returns_all_platforms_in_pid_order(self) -> None:
        first = Platform(
            pid="douyin",
            name="Douyin",
            extra={"region": "cn"},
        )
        second = self._build_platform(pid="wechat")

        self.manager.add_platform(first)
        self.manager.add_platform(second)

        platforms = self.manager.list_platform()

        self.assertEqual([platform.pid for platform in platforms], ["douyin", "wechat"])
        self.assertEqual([platform.name for platform in platforms], ["Douyin", "WeChat"])

    def test_edit_platform_updates_platform_fields(self) -> None:
        platform = self._build_platform()
        self.manager.add_platform(platform)
        original_created_time = platform.created_time
        original_updated_time = platform.updated_time

        updated_platform = Platform(
            pid="wechat-new",
            name="WeChat Pay",
            extra={"region": "global", "status": "active"},
        )

        self.manager.edit_platform(platform.pid, updated_platform)
        saved_platform = self.manager.get_platform(platform.pid)

        self.assertIsNotNone(saved_platform)
        assert saved_platform is not None
        self.assertEqual(saved_platform.pid, "wechat")
        self.assertEqual(saved_platform.name, "WeChat Pay")
        self.assertEqual(saved_platform.extra, {"region": "global", "status": "active"})
        self.assertEqual(saved_platform.created_time, original_created_time)
        self.assertGreaterEqual(saved_platform.updated_time, original_updated_time)

    def test_edit_platform_raises_when_missing(self) -> None:
        updated_platform = Platform(
            pid="ghost",
            name="Ghost Platform",
            extra={"region": "nowhere"},
        )

        with self.assertRaises(ValueError):
            self.manager.edit_platform("missing", updated_platform)

    def test_delete_platform_removes_record(self) -> None:
        platform = self._build_platform()
        self.manager.add_platform(platform)

        self.manager.delete_platform(platform.pid)

        self.assertIsNone(self.manager.get_platform(platform.pid))
        self.assertEqual(self.manager.list_platform(), [])

    def test_delete_platform_missing_is_no_op(self) -> None:
        self.manager.delete_platform("missing")
        self.assertEqual(self.manager.list_platform(), [])


if __name__ == "__main__":
    unittest.main()
