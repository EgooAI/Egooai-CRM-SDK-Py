from typing import Optional

from models import Platform

from .base import BaseManager


class PlatformManager(BaseManager[Platform]):
    """负责 Platform 表的连接初始化与增删改查操作。"""

    model = Platform
    pk_field = "pid"
    editable_fields = ("name", "extra")
    state_fields = ("created_time", "updated_time")
    touch_updated_time = True
    pk_is_auto = False

    def add_platform(self, platform: Platform) -> None:
        self._add(platform)

    def upsert_platform(self, platform: Platform) -> None:
        self._upsert(platform)

    def delete_platform(self, pid: str) -> None:
        self._delete(pid)

    def edit_platform(self, pid: str, platform: Platform) -> None:
        self._edit(pid, platform)

    def get_platform(self, pid: str) -> Optional[Platform]:
        return self._get(pid)

    def list_platform(self) -> list[Platform]:
        return self._list()


__all__ = ["PlatformManager"]
