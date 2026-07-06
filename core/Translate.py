from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from models.Translate import Translate

from . import bootstrap_engine


class TranslateManager:
    """负责 Translate 表的连接初始化与增删改查操作。"""

    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        """读取数据库配置、创建 engine，并在表缺失时自动建表。"""
        self.config_path, self.database_path, self.engine = bootstrap_engine(config_path)

    def add_translate(self, translate: Translate) -> None:
        """向 Translate 表新增一条翻译记录，并回填数据库生成的字段。"""
        with Session(self.engine) as session:
            session.add(translate)
            session.commit()
            session.refresh(translate)

    def delete_translate(self, tid: int) -> None:
        """按主键删除翻译记录；如果记录不存在则直接返回。"""
        with Session(self.engine) as session:
            translate = session.get(Translate, tid)
            if translate is None:
                return

            session.delete(translate)
            session.commit()

    def edit_translate(self, tid: int, translate: Translate) -> None:
        """按主键更新已有翻译记录的内容。"""
        with Session(self.engine) as session:
            current_translate = session.get(Translate, tid)
            if current_translate is None:
                raise ValueError(f"Translate {tid} not found")

            current_translate.content = translate.content

            session.add(current_translate)
            session.commit()
            session.refresh(current_translate)

    def get_translate(self, tid: int) -> Optional[Translate]:
        """按主键查询单条翻译记录，不存在时返回 None。"""
        with Session(self.engine) as session:
            return session.get(Translate, tid)

    def list_translate(self) -> list[Translate]:
        """查询并返回全部翻译记录，结果按 tid 升序排列。"""
        with Session(self.engine) as session:
            statement = select(Translate).order_by(Translate.tid)
            return list(session.exec(statement).all())


__all__ = ["TranslateManager"]
