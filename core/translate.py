from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from models.translate import Translate
from utils.common import bootstrap_engine, get_database_lock


class TranslateManager:
    """负责 Translate 表的连接初始化与增删改查操作。"""

    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        """读取数据库路径、获取共享 engine，并在表缺失时自动建表。"""
        self.database_path, self.engine = bootstrap_engine(database_path)
        self._lock = get_database_lock(self.database_path)

    @staticmethod
    def _payload_tuple(translate: Translate) -> tuple[object, ...]:
        return (translate.translation,)

    @staticmethod
    def _apply_translate_updates(current_translate: Translate, translate: Translate) -> None:
        current_translate.translation = translate.translation

    def add_translate(self, translate: Translate) -> None:
        """向 Translate 表新增一条翻译映射记录。"""
        with self._lock:
            with Session(self.engine) as session:
                session.add(translate)
                session.commit()
                session.refresh(translate)

    def upsert_translate(self, translate: Translate) -> None:
        """按主键执行 UPSERT；相同 payload 不会重复更新或插入。"""
        with self._lock:
            with Session(self.engine) as session:
                current_translate = session.get(Translate, translate.text_hash)
                if current_translate is None:
                    session.add(translate)
                    session.commit()
                    session.refresh(translate)
                    return

                if self._payload_tuple(current_translate) == self._payload_tuple(translate):
                    return

                self._apply_translate_updates(current_translate, translate)
                session.add(current_translate)
                session.commit()
                session.refresh(current_translate)

    def delete_translate(self, text_hash: str) -> None:
        """按主键删除翻译映射；如果记录不存在则直接返回。"""
        with self._lock:
            with Session(self.engine) as session:
                translate = session.get(Translate, text_hash)
                if translate is None:
                    return

                session.delete(translate)
                session.commit()

    def edit_translate(self, text_hash: str, translate: Translate) -> None:
        """按主键更新已有翻译映射的译文。"""
        with self._lock:
            with Session(self.engine) as session:
                current_translate = session.get(Translate, text_hash)
                if current_translate is None:
                    raise ValueError(f"Translate {text_hash} not found")

                self._apply_translate_updates(current_translate, translate)

                session.add(current_translate)
                session.commit()
                session.refresh(current_translate)

    def get_translate(self, text_hash: str) -> Optional[Translate]:
        """按主键查询单条翻译映射，不存在时返回 None。"""
        with Session(self.engine) as session:
            return session.get(Translate, text_hash)

    def list_translate(self) -> list[Translate]:
        """查询并返回全部翻译映射，结果按 text_hash 升序排列。"""
        with Session(self.engine) as session:
            statement = select(Translate).order_by(Translate.text_hash)
            return list(session.exec(statement).all())


__all__ = ["TranslateManager"]
