from pathlib import Path
from typing import Optional

from sqlmodel import Session

from models.meta import Meta
from utils.common import bootstrap_engine


class MetaManager:
    """负责 Meta 表的连接初始化与单例版本读写操作。"""

    SINGLETON_KEY = "version"

    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        """读取数据库路径、创建 engine，并在表缺失时自动建表。"""
        self.database_path, self.engine = bootstrap_engine(database_path)

    @staticmethod
    def _sync_meta_state(target: Meta, source: Meta) -> None:
        target.key = source.key
        target.value = source.value

    def _normalize_meta_key(self, key: Optional[str]) -> str:
        return key or self.SINGLETON_KEY

    def _get_or_create_meta(self, session: Session) -> Meta:
        """获取单例元数据记录；若不存在则创建默认记录。"""
        meta = session.get(Meta, self.SINGLETON_KEY)
        if meta is not None:
            return meta

        meta = Meta(key=self.SINGLETON_KEY)
        session.add(meta)
        session.commit()
        session.refresh(meta)
        return meta

    def get_version(self) -> str:
        """读取当前版本；若记录不存在则自动创建默认值并返回。"""
        with Session(self.engine) as session:
            meta = self._get_or_create_meta(session)
            return meta.value

    def upsert_meta(self, meta: Meta) -> None:
        """按 key 执行 UPSERT；相同 value 不会重复更新或插入。"""
        normalized_key = self._normalize_meta_key(meta.key)
        meta.key = normalized_key

        with Session(self.engine) as session:
            current_meta = session.get(Meta, normalized_key)
            if current_meta is None:
                session.add(meta)
                session.commit()
                session.refresh(meta)
                return

            if current_meta.value == meta.value:
                self._sync_meta_state(meta, current_meta)
                return

            current_meta.value = meta.value
            session.add(current_meta)
            session.commit()
            session.refresh(current_meta)
            self._sync_meta_state(meta, current_meta)

    def update_version(self, value: str) -> None:
        """更新当前版本；若记录不存在则先创建再更新。"""
        meta = Meta(key=self.SINGLETON_KEY, value=value)
        self.upsert_meta(meta)


__all__ = ["MetaManager"]
