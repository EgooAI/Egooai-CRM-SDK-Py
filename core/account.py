from typing import Optional

from models import Account

from .base import BaseManager


class AccountManager(BaseManager[Account]):
    """负责 Account 表的连接初始化与增删改查操作。"""

    model = Account
    pk_field = "aid"
    editable_fields = ("cid", "pid", "account", "nickname", "avatar", "sids", "extra")
    state_fields = ("created_time", "updated_time")
    touch_updated_time = True
    match_fields = ("cid", "pid", "account")

    def add_account(self, account: Account) -> None:
        self._add(account)

    def upsert_account(self, account: Account) -> None:
        self._upsert(account)

    def delete_account(self, aid: int) -> None:
        self._delete(aid)

    def edit_account(self, aid: int, account: Account) -> None:
        self._edit(aid, account)

    def get_account(self, aid: int) -> Optional[Account]:
        return self._get(aid)

    def list_account(self) -> list[Account]:
        return self._list()


__all__ = ["AccountManager"]
