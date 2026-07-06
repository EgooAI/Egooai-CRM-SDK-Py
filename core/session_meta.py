from pathlib import Path
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from models import SessionMeta
from models.customer import utc_now
from models.session_chat import (
    generate_session_chatid,
    get_session_chat_table,
    normalize_session_chatid,
    remove_session_chat_table,
)

from . import bootstrap_engine


class SessionMetaManager:
    """负责 SessionMeta 表的连接初始化与增删改查操作。"""

    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        """读取数据库路径、创建 engine，并在表缺失时自动建表。"""
        self.database_path, self.engine = bootstrap_engine(database_path)

    def add_session_meta(self, session_meta: SessionMeta) -> None:
        """向 SessionMeta 表新增一条会话元数据记录，并回填数据库生成的字段。"""
        max_attempts = 3
        for attempt in range(max_attempts):
            session_meta.chatid = normalize_session_chatid(session_meta.chatid or generate_session_chatid())
            get_session_chat_table(session_meta.chatid).create(self.engine, checkfirst=True)

            with Session(self.engine) as session:
                try:
                    session.add(session_meta)
                    session.commit()
                    session.refresh(session_meta)
                    return
                except IntegrityError as exc:
                    session.rollback()
                    if "chatid" not in str(exc).lower() or attempt == max_attempts - 1:
                        raise
                    session_meta.chatid = generate_session_chatid()

    def delete_session_meta(self, sid: int) -> None:
        """按主键删除会话元数据，并同步删除对应的聊天表。"""
        session_chat_table = None
        chatid = None

        with Session(self.engine) as session:
            session_meta = session.get(SessionMeta, sid)
            if session_meta is None:
                return

            chatid = session_meta.chatid
            session_chat_table = get_session_chat_table(chatid)
            session_chat_table.drop(session.connection(), checkfirst=True)
            session.delete(session_meta)
            session.commit()

        if chatid is not None:
            remove_session_chat_table(chatid)

    def edit_session_meta(self, sid: int, session_meta: SessionMeta) -> None:
        """按主键更新已有会话元数据的可编辑字段，并刷新更新时间。"""
        with Session(self.engine) as session:
            current_session_meta = session.get(SessionMeta, sid)
            if current_session_meta is None:
                raise ValueError(f"SessionMeta {sid} not found")

            current_session_meta.name = session_meta.name
            current_session_meta.participants = session_meta.participants
            current_session_meta.updated_time = utc_now()

            session.add(current_session_meta)
            session.commit()
            session.refresh(current_session_meta)

    def get_session_meta(self, sid: int) -> Optional[SessionMeta]:
        """按主键查询单条会话元数据，不存在时返回 None。"""
        with Session(self.engine) as session:
            return session.get(SessionMeta, sid)

    def list_session_meta(self) -> list[SessionMeta]:
        """查询并返回全部会话元数据记录，结果按 sid 升序排列。"""
        with Session(self.engine) as session:
            statement = select(SessionMeta).order_by(SessionMeta.sid)
            return list(session.exec(statement).all())


__all__ = ["SessionMetaManager"]
