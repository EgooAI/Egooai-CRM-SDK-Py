from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from models.platform import Platform
from utils.common import bootstrap_engine, utc_now


class PlatformManager:
    """负责 Platform 表的连接初始化与增删改查操作。"""

    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        """读取数据库路径、创建 engine，并在表缺失时自动建表。"""
        self.database_path, self.engine = bootstrap_engine(database_path)

    @staticmethod
    def _payload_tuple(platform: Platform) -> tuple[object, ...]:
        return (platform.name, platform.extra)

    @staticmethod
    def _sync_platform_state(target: Platform, source: Platform) -> None:
        target.pid = source.pid
        target.created_time = source.created_time
        target.updated_time = source.updated_time

    @staticmethod
    def _apply_platform_updates(current_platform: Platform, platform: Platform) -> None:
        current_platform.name = platform.name
        current_platform.extra = platform.extra
        current_platform.updated_time = utc_now()

    def add_platform(self, platform: Platform) -> None:
        """向 Platform 表新增一条平台记录，并回填数据库生成的字段。"""
        with Session(self.engine) as session:
            session.add(platform)
            session.commit()
            session.refresh(platform)

    def upsert_platform(self, platform: Platform) -> None:
        """按主键执行 UPSERT；相同 payload 不会重复更新或插入。"""
        with Session(self.engine) as session:
            current_platform = session.get(Platform, platform.pid)
            if current_platform is None:
                session.add(platform)
                session.commit()
                session.refresh(platform)
                return

            if self._payload_tuple(current_platform) == self._payload_tuple(platform):
                self._sync_platform_state(platform, current_platform)
                return

            self._apply_platform_updates(current_platform, platform)
            session.add(current_platform)
            session.commit()
            session.refresh(current_platform)
            self._sync_platform_state(platform, current_platform)

    def delete_platform(self, pid: str) -> None:
        """按主键删除平台；如果记录不存在则直接返回。"""
        with Session(self.engine) as session:
            platform = session.get(Platform, pid)
            if platform is None:
                return

            session.delete(platform)
            session.commit()

    def edit_platform(self, pid: str, platform: Platform) -> None:
        """按主键更新已有平台的可编辑字段，并刷新更新时间。"""
        with Session(self.engine) as session:
            current_platform = session.get(Platform, pid)
            if current_platform is None:
                raise ValueError(f"Platform {pid} not found")

            self._apply_platform_updates(current_platform, platform)

            session.add(current_platform)
            session.commit()
            session.refresh(current_platform)

    def get_platform(self, pid: str) -> Optional[Platform]:
        """按主键查询单个平台，不存在时返回 None。"""
        with Session(self.engine) as session:
            return session.get(Platform, pid)

    def list_platform(self) -> list[Platform]:
        """查询并返回全部平台记录，结果按 pid 升序排列。"""
        with Session(self.engine) as session:
            statement = select(Platform).order_by(Platform.pid)
            return list(session.exec(statement).all())


__all__ = ["PlatformManager"]
