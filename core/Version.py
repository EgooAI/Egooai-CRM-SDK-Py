from pathlib import Path
from typing import Optional

from sqlmodel import Session

from models.Version import Version

from . import bootstrap_engine


class VersionManager:
    """负责 Version 表的连接初始化与单例版本读写操作。"""

    SINGLETON_KEY = "version"

    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        """读取数据库配置、创建 engine，并在表缺失时自动建表。"""
        self.config_path, self.database_path, self.engine = bootstrap_engine(config_path)

    def _get_or_create_version(self, session: Session) -> Version:
        """获取单例版本记录；若不存在则创建默认记录。"""
        version = session.get(Version, self.SINGLETON_KEY)
        if version is not None:
            return version

        version = Version(key=self.SINGLETON_KEY)
        session.add(version)
        session.commit()
        session.refresh(version)
        return version

    def get_version(self) -> str:
        """读取当前版本；若记录不存在则自动创建默认值并返回。"""
        with Session(self.engine) as session:
            version = self._get_or_create_version(session)
            return version.value

    def update_version(self, value: str) -> None:
        """更新当前版本；若记录不存在则先创建再更新。"""
        with Session(self.engine) as session:
            version = self._get_or_create_version(session)
            version.value = value

            session.add(version)
            session.commit()
            session.refresh(version)


__all__ = ["VersionManager"]
