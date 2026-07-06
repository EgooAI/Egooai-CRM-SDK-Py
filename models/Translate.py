from sqlmodel import Field, SQLModel


class Translate(SQLModel, table=True):
    text_hash: str = Field(primary_key=True)
    translation: str


__all__ = ["Translate"]
