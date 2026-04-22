from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from uuid6 import uuid7


def _uuid_str() -> str:
    return str(uuid7())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    @declared_attr.directive
    def __tablename__(cls) -> str:
        name = cls.__name__
        out = [name[0].lower()]
        for ch in name[1:]:
            if ch.isupper():
                out.append("_")
                out.append(ch.lower())
            else:
                out.append(ch)
        return "".join(out) + "s"


class IdMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)


class TimestampsMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
