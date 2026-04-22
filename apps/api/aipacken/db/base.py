from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, func
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
    # server_default=func.now() guarantees the DB stamps the row even
    # when an insert comes from raw SQL, a data migration, or an
    # Alembic op that bypasses the ORM. The python-side default is
    # retained so ORM inserts still carry a timezone-aware datetime
    # locally; both converge on UTC.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
