from typing import Optional

from models import Customer

from .base import BaseManager


class CustomerManager(BaseManager[Customer]):
    """负责 Customer 表的连接初始化与增删改查操作。"""

    model = Customer
    pk_field = "cid"
    editable_fields = ("name", "sex", "birthdate", "region", "extra", "image")
    state_fields = ("created_time", "updated_time")
    touch_updated_time = True
    match_fields = ()

    def add_customer(self, customer: Customer) -> None:
        self._add(customer)

    def upsert_customer(self, customer: Customer) -> None:
        self._upsert(customer)

    def delete_customer(self, cid: int) -> None:
        self._delete(cid)

    def edit_customer(self, cid: int, customer: Customer) -> None:
        self._edit(cid, customer)

    def get_customer(self, cid: int) -> Optional[Customer]:
        return self._get(cid)

    def list_customer(self) -> list[Customer]:
        return self._list()


__all__ = ["CustomerManager"]
