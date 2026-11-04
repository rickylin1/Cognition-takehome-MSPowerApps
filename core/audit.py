"""Append-only audit log. This module intentionally exposes no update or delete functions."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from core.auth import User
from core.db import Base


class AuditEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    before: Mapped[Any | None] = mapped_column(JSON)
    after: Mapped[Any | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[User | None] = relationship(lazy="joined")


def log(
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: Any,
    before: Any = None,
    after: Any = None,
    reason: str | None = None,
) -> AuditEntry:
    """Add an audit entry to the caller's transaction. The caller commits."""
    entry = AuditEntry(
        timestamp=datetime.now(timezone.utc),
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before=before,
        after=after,
        reason=reason,
    )
    db.add(entry)
    db.flush()
    return entry


def list_entries(db: Session) -> list[AuditEntry]:
    return list(db.scalars(select(AuditEntry).order_by(AuditEntry.id.desc())))
