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

    def add_platform(self, platform: Platform) -> None:
        """向 Platform 表新增一条平台记录，并回填数据库生成的字段。"""
        with Session(self.engine) as session:
            session.add(platform)
            session.commit()
            session.refresh(platform)

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

            current_platform.name = platform.name
            current_platform.extra = platform.extra
            current_platform.updated_time = utc_now()

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
