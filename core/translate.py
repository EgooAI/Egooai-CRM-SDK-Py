from typing import Optional

from models import Translate

from .base import BaseManager


class TranslateManager(BaseManager[Translate]):
    """负责 Translate 表的连接初始化与增删改查操作。"""

    model = Translate
    pk_field = "text_hash"
    editable_fields = ("translation",)
    pk_is_auto = False

    def add_translate(self, translate: Translate) -> None:
        self._add(translate)

    def upsert_translate(self, translate: Translate) -> None:
        self._upsert(translate)

    def delete_translate(self, text_hash: str) -> None:
        self._delete(text_hash)

    def edit_translate(self, text_hash: str, translate: Translate) -> None:
        self._edit(text_hash, translate)

    def get_translate(self, text_hash: str) -> Optional[Translate]:
        return self._get(text_hash)

    def list_translate(self) -> list[Translate]:
        return self._list()


__all__ = ["TranslateManager"]
