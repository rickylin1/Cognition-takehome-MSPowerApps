"""Transactions, refunds, and the refund rules. Amounts are stored in integer cents."""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from apps.refunds.permissions import REFUND_APPROVE
from config import refunds as refunds_config
from core import approvals, audit
from core.auth import User
from core.db import Base

SETTLED = "SETTLED"
PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
REFUNDED = "REFUNDED"

ISSUED = "ISSUED"
PENDING_APPROVAL = "PENDING_APPROVAL"
REJECTED = "REJECTED"


class RefundError(Exception):
    """A refund that breaks a refund rule. Routes show the message to the user."""


class InvalidAmount(RefundError):
    pass


class ExceedsRefundable(RefundError):
    pass


class NotPending(RefundError):
    pass


class Transaction(Base):
    __tablename__ = "refunds_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(128))
    amount_cents: Mapped[int]
    date: Mapped[date] = mapped_column(Date)
    merchant: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default=SETTLED)


class Refund(Base):
    __tablename__ = "refunds_refunds"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("refunds_transactions.id"))
    amount_cents: Mapped[int]
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime)


def threshold_cents() -> int:
    return int(refunds_config.APPROVAL_THRESHOLD * 100)


def parse_amount(text: str) -> int:
    """Parse a dollar amount like "700" or "700.50" into cents."""
    try:
        amount = Decimal((text or "").strip())
    except InvalidOperation:
        raise InvalidAmount("Enter the amount as a number, e.g. 125.00.") from None
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.01")):
        raise InvalidAmount("The amount must be positive with at most two decimal places.")
    return int(amount * 100)


def refunds_for(db: Session, transaction: Transaction) -> list[Refund]:
    return list(db.scalars(
        select(Refund).where(Refund.transaction_id == transaction.id).order_by(Refund.id)
    ))


def issued_cents(db: Session, transaction: Transaction) -> int:
    return sum(r.amount_cents for r in refunds_for(db, transaction) if r.status == ISSUED)


def refundable_cents(db: Session, transaction: Transaction) -> int:
    return transaction.amount_cents - issued_cents(db, transaction)


def _state(refund: Refund) -> dict:
    return {"status": refund.status, "amount_cents": refund.amount_cents,
            "transaction_id": refund.transaction_id}


def _issue(db: Session, actor: User, refund: Refund, transaction: Transaction) -> None:
    """Record the (mocked) payout and update the transaction's refund status."""
    before = _state(refund)
    refund.status = ISSUED
    refund.issued_at = datetime.now(timezone.utc)
    db.flush()
    audit.log(db, actor, "refunds.refund.issued", "refunds_refund", refund.id,
              before=before, after=_state(refund), reason=refund.reason)

    tx_before = {"status": transaction.status}
    transaction.status = REFUNDED if refundable_cents(db, transaction) == 0 else PARTIALLY_REFUNDED
    if transaction.status != tx_before["status"]:
        db.flush()
        audit.log(db, actor, "refunds.transaction.status_changed", "refunds_transaction",
                  transaction.id, before=tx_before, after={"status": transaction.status},
                  reason=f"Refund #{refund.id} issued")


def request_refund(
    db: Session, actor: User, transaction: Transaction, amount_cents: int, reason: str
) -> Refund:
    """Request a refund. Does not commit.

    amount <= threshold -> ISSUED immediately
    amount >  threshold -> PENDING_APPROVAL, via an approval request
    """
    reason = (reason or "").strip()
    if not reason:
        raise RefundError("A reason is required.")
    if amount_cents <= 0:
        raise InvalidAmount("The amount must be positive.")
    remaining = refundable_cents(db, transaction)
    if amount_cents > remaining:
        raise ExceedsRefundable(
            f"The refund exceeds the refundable amount (${remaining / 100:,.2f})."
        )

    refund = Refund(
        transaction_id=transaction.id, amount_cents=amount_cents, reason=reason,
        status=PENDING_APPROVAL, requested_by_id=actor.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(refund)
    db.flush()
    audit.log(db, actor, "refunds.refund.requested", "refunds_refund", refund.id,
              after=_state(refund), reason=reason)

    if amount_cents <= threshold_cents():
        _issue(db, actor, refund, transaction)
    else:
        req = approvals.request(
            db, actor, "refunds.refund", "refunds_refund", refund.id,
            payload={"transaction_id": transaction.id, "amount_cents": amount_cents},
            approver_permission=REFUND_APPROVE,
        )
        refund.approval_id = req.id
        db.flush()
    return refund


def decide_refund(db: Session, actor: User, refund: Refund, decision: str, reason: str) -> Refund:
    """Approve or reject a pending refund. Does not commit. core.approvals enforces the
    approver permission and that the approver is not the requester."""
    if decision not in (approvals.APPROVED, approvals.REJECTED):
        raise RefundError(f"Invalid decision: {decision}")
    reason = (reason or "").strip()
    if not reason:
        raise RefundError("A reason is required.")
    if refund.status != PENDING_APPROVAL:
        raise NotPending(f"Refund #{refund.id} is {refund.status} and cannot be decided.")

    transaction = db.get(Transaction, refund.transaction_id)
    if decision == approvals.APPROVED and refund.amount_cents > refundable_cents(db, transaction):
        raise ExceedsRefundable(
            "The refund now exceeds the refundable amount "
            f"(${refundable_cents(db, transaction) / 100:,.2f}); reject it instead."
        )

    approvals.decide(db, actor, refund.approval_id, decision, reason)
    before = _state(refund)
    if decision == approvals.APPROVED:
        audit.log(db, actor, "refunds.refund.approved", "refunds_refund", refund.id,
                  before=before, after=before, reason=reason)
        _issue(db, actor, refund, transaction)
    else:
        refund.status = REJECTED
        db.flush()
        audit.log(db, actor, "refunds.refund.rejected", "refunds_refund", refund.id,
                  before=before, after=_state(refund), reason=reason)
    return refund
