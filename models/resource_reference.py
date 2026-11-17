"""Associates a resource with an opaque, caller-owned identity."""

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class ResourceReference(SQLModel, table=True):
    __tablename__ = "resource_reference"
    __table_args__ = (UniqueConstraint("namespace", "owner_type", "owner_id", "slot"),)

    reference_id: str = Field(primary_key=True)
    namespace: str
    owner_type: str
    owner_id: str
    slot: str
    resource_id: str = Field(foreign_key="resource.resource_id", index=True)
    expires_at: float | None = None


__all__ = ["ResourceReference"]
