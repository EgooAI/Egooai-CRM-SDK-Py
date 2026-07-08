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
        self.db_path = self.temp_path / "translate.sqlite"
        self.manager = TranslateManager(database_path=self.db_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        self.temp_dir.cleanup()

    def _build_translate(
        self,
        text_hash: str = "文本摘要值",
        translation: str = "translated text",
    ) -> Translate:
        return Translate(text_hash=text_hash, translation=translation)

    def test_auto_creates_translate_table(self) -> None:
        self.assertTrue(self.db_path.exists())

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()

        self.assertIn("translate", tables)

    def test_add_translate_persists_primary_key(self) -> None:
        translate = self._build_translate()

        self.manager.add_translate(translate)

        self.assertEqual(translate.text_hash, "文本摘要值")

    def test_get_translate_returns_inserted_translate(self) -> None:
        translate = self._build_translate()
        self.manager.add_translate(translate)

        saved_translate = self.manager.get_translate(translate.text_hash)

        self.assertIsNotNone(saved_translate)
        assert saved_translate is not None
        self.assertEqual(saved_translate.text_hash, "文本摘要值")
        self.assertEqual(saved_translate.translation, "translated text")

    def test_get_translate_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.manager.get_translate("missing"))

    def test_list_translate_returns_all_translates_in_text_hash_order(self) -> None:
        first = self._build_translate(text_hash="a-summary", translation="hello")
        second = self._build_translate(text_hash="b-summary", translation="bye")

        self.manager.add_translate(first)
        self.manager.add_translate(second)

        translates = self.manager.list_translate()

        self.assertEqual(
            [translate.text_hash for translate in translates],
            ["a-summary", "b-summary"],
        )
        self.assertEqual(
            [translate.translation for translate in translates],
            ["hello", "bye"],
        )

    def test_edit_translate_updates_translation(self) -> None:
        translate = self._build_translate()
        self.manager.add_translate(translate)

        updated_translate = Translate(text_hash="ignored", translation="updated text")

        self.manager.edit_translate(translate.text_hash, updated_translate)
        saved_translate = self.manager.get_translate(translate.text_hash)

        self.assertIsNotNone(saved_translate)
        assert saved_translate is not None
        self.assertEqual(saved_translate.text_hash, "文本摘要值")
        self.assertEqual(saved_translate.translation, "updated text")

    def test_edit_translate_raises_when_missing(self) -> None:
        updated_translate = Translate(text_hash="不存在", translation="missing")

        with self.assertRaises(ValueError):
            self.manager.edit_translate("不存在", updated_translate)

    def test_delete_translate_removes_record(self) -> None:
        translate = self._build_translate()
        self.manager.add_translate(translate)

        self.manager.delete_translate(translate.text_hash)

        self.assertIsNone(self.manager.get_translate(translate.text_hash))
        self.assertEqual(self.manager.list_translate(), [])

    def test_delete_translate_missing_is_no_op(self) -> None:
        self.manager.delete_translate("missing")
        self.assertEqual(self.manager.list_translate(), [])

    def test_upsert_translate_inserts_when_missing(self) -> None:
        translate = self._build_translate(text_hash="hash-upsert", translation="hello")

        self.manager.upsert_translate(translate)

        self.assertEqual(translate.text_hash, "hash-upsert")
        self.assertEqual(len(self.manager.list_translate()), 1)

    def test_upsert_translate_updates_existing_record(self) -> None:
        translate = self._build_translate()
        self.manager.add_translate(translate)
        updated_translate = Translate(text_hash=translate.text_hash, translation="updated text")

        self.manager.upsert_translate(updated_translate)
        saved_translate = self.manager.get_translate(translate.text_hash)

        self.assertIsNotNone(saved_translate)
        assert saved_translate is not None
        self.assertEqual(saved_translate.translation, "updated text")
        self.assertEqual(len(self.manager.list_translate()), 1)

    def test_upsert_translate_skips_duplicate_payload(self) -> None:
        translate = self._build_translate()
        self.manager.add_translate(translate)
        duplicate_translate = Translate(text_hash=translate.text_hash, translation=translate.translation)

        self.manager.upsert_translate(duplicate_translate)

        self.assertEqual(len(self.manager.list_translate()), 1)
        saved_translate = self.manager.get_translate(translate.text_hash)
        self.assertIsNotNone(saved_translate)
        assert saved_translate is not None
        self.assertEqual(saved_translate.translation, "translated text")


if __name__ == "__main__":
    unittest.main()
