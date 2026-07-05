from datetime import timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from models import SessionChat, SessionMeta
from models.Customer import utc_now
from models.SessionChat import get_session_chat_table

from . import bootstrap_engine


class SessionChatManager:
    """负责按 chatid 动态创建会话聊天表并执行增删改查。"""

    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        """读取数据库配置、创建 engine，并完成静态表初始化。"""
        self.config_path, self.database_path, self.engine = bootstrap_engine(config_path)

    def ensure_session_chat_table(self, chatid: str) -> str:
        """确保指定 chatid 对应的聊天表存在，并返回物理表名。"""
        session_chat_table = get_session_chat_table(chatid)
        session_chat_table.create(self.engine, checkfirst=True)
        return session_chat_table.name

    def add_session_chat(self, chatid: str, chat: SessionChat) -> None:
        """向指定聊天表新增一条消息，并回填数据库生成的字段。"""
        session_chat_table = get_session_chat_table(chatid)
        session_chat_table.create(self.engine, checkfirst=True)

        payload = {
            "sender": chat.sender,
            "type": chat.type,
            "content": chat.content,
            "read": chat.read,
            "created_time": chat.created_time,
            "updated_time": chat.updated_time,
        }

        with Session(self.engine) as session:
            result = session.exec(session_chat_table.insert().values(**payload))
            session.commit()
            chat.id = result.lastrowid

    def add_session_chat_by_sid(self, sid: int, chat: SessionChat) -> None:
        """按 sid 定位会话后，向对应聊天表新增一条消息。"""
        chatid = self._get_chatid_by_sid(sid)
        self.add_session_chat(chatid, chat)

    def delete_session_chat(self, chatid: str, chat_id: int) -> None:
        """按主键删除指定聊天表中的消息；如果记录不存在则直接返回。"""
        session_chat_table = get_session_chat_table(chatid)
        session_chat_table.create(self.engine, checkfirst=True)

        with Session(self.engine) as session:
            existing_row = session.exec(
                session_chat_table.select().where(session_chat_table.c.id == chat_id)
            ).first()
            if existing_row is None:
                return

            session.exec(session_chat_table.delete().where(session_chat_table.c.id == chat_id))
            session.commit()

    def delete_session_chat_by_sid(self, sid: int, chat_id: int) -> None:
        """按 sid 定位会话后，删除对应聊天表中的消息。"""
        chatid = self._get_chatid_by_sid(sid)
        self.delete_session_chat(chatid, chat_id)

    def edit_session_chat(self, chatid: str, chat_id: int, chat: SessionChat) -> None:
        """按主键更新指定聊天表中的消息字段，并刷新更新时间。"""
        session_chat_table = get_session_chat_table(chatid)
        session_chat_table.create(self.engine, checkfirst=True)

        updated_time = utc_now()
        with Session(self.engine) as session:
            existing_row = session.exec(
                session_chat_table.select().where(session_chat_table.c.id == chat_id)
            ).first()
            if existing_row is None:
                raise ValueError(f"SessionChat {chat_id} not found in {session_chat_table.name}")

            session.exec(
                session_chat_table.update()
                .where(session_chat_table.c.id == chat_id)
                .values(
                    sender=chat.sender,
                    type=chat.type,
                    content=chat.content,
                    read=chat.read,
                    updated_time=updated_time,
                )
            )
            session.commit()
            chat.id = chat_id
            chat.updated_time = updated_time

    def edit_session_chat_by_sid(self, sid: int, chat_id: int, chat: SessionChat) -> None:
        """按 sid 定位会话后，更新对应聊天表中的消息。"""
        chatid = self._get_chatid_by_sid(sid)
        self.edit_session_chat(chatid, chat_id, chat)

    def get_session_chat(self, chatid: str, chat_id: int) -> Optional[SessionChat]:
        """按主键查询指定聊天表中的消息，不存在时返回 None。"""
        session_chat_table = get_session_chat_table(chatid)
        session_chat_table.create(self.engine, checkfirst=True)

        with Session(self.engine) as session:
            row = session.exec(
                session_chat_table.select().where(session_chat_table.c.id == chat_id)
            ).first()
            if row is None:
                return None
            return self._build_session_chat(row)

    def get_session_chat_by_sid(self, sid: int, chat_id: int) -> Optional[SessionChat]:
        """按 sid 定位会话后，查询对应聊天表中的单条消息。"""
        chatid = self._get_chatid_by_sid(sid)
        return self.get_session_chat(chatid, chat_id)

    def list_session_chat(self, chatid: str) -> list[SessionChat]:
        """查询并返回指定聊天表中的全部消息，结果按 id 升序排列。"""
        session_chat_table = get_session_chat_table(chatid)
        session_chat_table.create(self.engine, checkfirst=True)

        with Session(self.engine) as session:
            rows = session.exec(session_chat_table.select().order_by(session_chat_table.c.id)).all()
            return [self._build_session_chat(row) for row in rows]

    def list_session_chat_by_sid(self, sid: int) -> list[SessionChat]:
        """按 sid 定位会话后，查询对应聊天表中的全部消息。"""
        chatid = self._get_chatid_by_sid(sid)
        return self.list_session_chat(chatid)

    def _get_chatid_by_sid(self, sid: int) -> str:
        with Session(self.engine) as session:
            session_meta = session.get(SessionMeta, sid)
            if session_meta is None:
                raise ValueError(f"SessionMeta {sid} not found")
            return session_meta.chatid

    @staticmethod
    def _build_session_chat(row) -> SessionChat:
        row_mapping = row._mapping
        created_time = SessionChatManager._ensure_utc_datetime(row_mapping["created_time"])
        updated_time = SessionChatManager._ensure_utc_datetime(row_mapping["updated_time"])
        return SessionChat(
            id=row_mapping["id"],
            sender=row_mapping["sender"],
            type=row_mapping["type"],
            content=row_mapping["content"],
            read=row_mapping["read"],
            created_time=created_time,
            updated_time=updated_time,
        )

    @staticmethod
    def _ensure_utc_datetime(value):
        if value.tzinfo is not None:
            return value
        return value.replace(tzinfo=timezone.utc)


__all__ = ["SessionChatManager"]
