import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core import TranslateManager
from models import Translate


class TranslateManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.config_path = self.temp_path / "sql.yml"
        self.db_path = self.temp_path / "translate.sqlite"
        self.config_path.write_text("type: sqlite\npath: ./translate.sqlite\n", encoding="utf-8")
        self.manager = TranslateManager(config_path=self.config_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.temp_dir.cleanup()

    def _build_translate(self, content: dict | None = None) -> Translate:
        return Translate(content=content or {"zh-CN": "你好", "en-US": "hello"})

    def test_auto_creates_translate_table(self) -> None:
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

        self.assertIn("translate", tables)

    def test_add_translate_populates_primary_key(self) -> None:
        translate = self._build_translate()

        self.manager.add_translate(translate)

        self.assertIsNotNone(translate.tid)

    def test_get_translate_returns_inserted_translate(self) -> None:
        translate = self._build_translate()
        self.manager.add_translate(translate)

        saved_translate = self.manager.get_translate(translate.tid)

        self.assertIsNotNone(saved_translate)
        assert saved_translate is not None
        self.assertEqual(saved_translate.content, {"zh-CN": "你好", "en-US": "hello"})

    def test_get_translate_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.get_translate(9999))

    def test_list_translate_returns_all_translates_in_tid_order(self) -> None:
        first = self._build_translate(content={"zh-CN": "你好", "en-US": "hello"})
        second = self._build_translate(content={"zh-CN": "再见", "en-US": "bye"})

        self.manager.add_translate(first)
        self.manager.add_translate(second)

        translates = self.manager.list_translate()

        self.assertEqual([translate.tid for translate in translates], [first.tid, second.tid])
        self.assertEqual(
            [translate.content for translate in translates],
            [{"zh-CN": "你好", "en-US": "hello"}, {"zh-CN": "再见", "en-US": "bye"}],
        )

    def test_edit_translate_updates_content(self) -> None:
        translate = self._build_translate()
        self.manager.add_translate(translate)

        updated_translate = Translate(content={"zh-CN": "谢谢", "en-US": "thanks"})

        self.manager.edit_translate(translate.tid, updated_translate)
        saved_translate = self.manager.get_translate(translate.tid)

        self.assertIsNotNone(saved_translate)
        assert saved_translate is not None
        self.assertEqual(saved_translate.content, {"zh-CN": "谢谢", "en-US": "thanks"})

    def test_edit_translate_raises_when_missing(self) -> None:
        updated_translate = Translate(content={"zh-CN": "不存在", "en-US": "missing"})

        with self.assertRaises(ValueError):
            self.manager.edit_translate(404, updated_translate)

    def test_delete_translate_removes_record(self) -> None:
        translate = self._build_translate()
        self.manager.add_translate(translate)

        self.manager.delete_translate(translate.tid)

        self.assertIsNone(self.manager.get_translate(translate.tid))
        self.assertEqual(self.manager.list_translate(), [])

    def test_delete_translate_missing_is_no_op(self) -> None:
        self.manager.delete_translate(404)
        self.assertEqual(self.manager.list_translate(), [])


if __name__ == "__main__":
    unittest.main()
