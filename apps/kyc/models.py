"""KYC cases and their status rules."""

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from apps.kyc.permissions import CASE_SECOND_REVIEW
from core import approvals, audit
from core.auth import User
from core.db import Base

PENDING = "PENDING"
PENDING_SECOND_REVIEW = "PENDING_SECOND_REVIEW"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
DECISIONS = (APPROVED, REJECTED)


class KycError(Exception):
    """A decision that breaks a KYC rule. Routes show the message to the user."""


class InvalidTransition(KycError):
    pass


class KycCase(Base):
    __tablename__ = "kyc_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_name: Mapped[str] = mapped_column(String(128))
    date_of_birth: Mapped[date] = mapped_column(Date)
    ssn: Mapped[str] = mapped_column(String(11))
    address: Mapped[str] = mapped_column(String(256))
    id_document_type: Mapped[str] = mapped_column(String(64))
    document_check_passed: Mapped[bool]
    identity_match_passed: Mapped[bool]
    watchlist_hit: Mapped[bool]
    status: Mapped[str] = mapped_column(String(32), default=PENDING)
    proposed_decision: Mapped[str | None] = mapped_column(String(16))
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


def _state(case: KycCase) -> dict:
    return {"status": case.status, "proposed_decision": case.proposed_decision}


def decide(db: Session, actor: User, case: KycCase, decision: str, reason: str) -> KycCase:
    """Apply an analyst's or second reviewer's decision. Does not commit.

    PENDING (no watchlist hit)  -> APPROVED | REJECTED
    PENDING (watchlist hit)     -> PENDING_SECOND_REVIEW, via an approval request
    PENDING_SECOND_REVIEW       -> APPROVED | REJECTED, decided by a different user
                                   with kyc:case.second_review (enforced by core.approvals)
    """
    if decision not in DECISIONS:
        raise KycError(f"Invalid decision: {decision}")
    reason = (reason or "").strip()
    if not reason:
        raise KycError("A reason is required.")

    before = _state(case)
    if case.status == PENDING and case.watchlist_hit:
        req = approvals.request(
            db, actor, "kyc.case_decision", "kyc_case", case.id,
            payload={"proposed_decision": decision}, approver_permission=CASE_SECOND_REVIEW,
        )
        case.status = PENDING_SECOND_REVIEW
        case.proposed_decision = decision
        case.approval_id = req.id
        action = "kyc.case.submitted_for_second_review"
    elif case.status == PENDING:
        case.status = decision
        action = "kyc.case.decided"
    elif case.status == PENDING_SECOND_REVIEW:
        # The second reviewer decides the case; the approval records whether they agreed
        # with the proposed decision.
        outcome = approvals.APPROVED if decision == case.proposed_decision else approvals.REJECTED
        approvals.decide(db, actor, case.approval_id, outcome, reason)
        case.status = decision
        action = "kyc.case.second_review_decided"
    else:
        raise InvalidTransition(f"Case {case.id} is {case.status} and cannot be decided.")

    case.updated_at = datetime.now(timezone.utc)
    db.flush()
    audit.log(db, actor, action, "kyc_case", case.id, before=before, after=_state(case),
              reason=reason)
    return case
