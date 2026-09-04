from typing import Optional

from models import AccountMapping

from .base import BaseManager


class AccountMappingManager(BaseManager[AccountMapping]):
    """负责 AccountMapping 表的连接初始化与增删改查操作。"""

    model = AccountMapping
    pk_field = "amid"
    editable_fields = ("aid", "type", "key")
    match_fields = ()

    def add_account_mapping(self, account_mapping: AccountMapping) -> None:
        self._add(account_mapping)

    def upsert_account_mapping(self, account_mapping: AccountMapping) -> None:
        self._upsert(account_mapping)

    def delete_account_mapping(self, amid: int) -> None:
        self._delete(amid)

    def edit_account_mapping(self, amid: int, account_mapping: AccountMapping) -> None:
        self._edit(amid, account_mapping)

    def get_account_mapping(self, amid: int) -> Optional[AccountMapping]:
        return self._get(amid)

    def list_account_mapping(self) -> list[AccountMapping]:
        return self._list()


__all__ = ["AccountMappingManager"]
