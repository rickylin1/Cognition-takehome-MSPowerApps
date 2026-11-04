"""Four-eyes approvals. The approver can never be the requester."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from core import audit
from core.auth import User
from core.db import Base
from core.permissions import PermissionDenied, has_permission

PENDING = "PENDING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"


class ApprovalError(Exception):
    """Raised when an approval request cannot be decided (e.g. already decided)."""


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[Any | None] = mapped_column(JSON)
    approver_permission: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default=PENDING)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    decision_reason: Mapped[str | None] = mapped_column(Text)


def _snapshot(req: ApprovalRequest) -> dict[str, Any]:
    return {
        "status": req.status,
        "requested_by_id": req.requested_by_id,
        "decided_by_id": req.decided_by_id,
    }


def request(
    db: Session,
    actor: User,
    type: str,
    entity_type: str,
    entity_id: Any,
    payload: Any,
    approver_permission: str,
) -> ApprovalRequest:
    req = ApprovalRequest(
        type=type,
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload=payload,
        approver_permission=approver_permission,
        status=PENDING,
        requested_by_id=actor.id,
        requested_at=datetime.now(timezone.utc),
    )
    db.add(req)
    db.flush()
    audit.log(
        db, actor, "approval.requested", "approval_request", req.id,
        after={**_snapshot(req), "type": type, "entity_type": entity_type,
               "entity_id": req.entity_id, "payload": payload},
    )
    return req


def decide(
    db: Session, actor: User, approval_id: int, decision: str, reason: str
) -> ApprovalRequest:
    """Decide a pending request. Does not commit: the caller applies the outcome to its
    own entity and commits in the same transaction."""
    req = db.get(ApprovalRequest, approval_id)
    if req is None:
        raise ApprovalError(f"Approval request {approval_id} not found")
    if decision not in (APPROVED, REJECTED):
        raise ApprovalError(f"Invalid decision: {decision}")
    if req.status != PENDING:
        raise ApprovalError(f"Approval request {approval_id} is already {req.status}")
    if not has_permission(actor, req.approver_permission):
        raise PermissionDenied(req.approver_permission)
    if actor.id == req.requested_by_id:
        raise PermissionDenied("The requester cannot decide their own approval request")

    before = _snapshot(req)
    req.status = decision
    req.decided_by_id = actor.id
    req.decided_at = datetime.now(timezone.utc)
    req.decision_reason = reason
    db.flush()
    audit.log(
        db, actor, f"approval.{decision.lower()}", "approval_request", req.id,
        before=before, after=_snapshot(req), reason=reason,
    )
    return req
