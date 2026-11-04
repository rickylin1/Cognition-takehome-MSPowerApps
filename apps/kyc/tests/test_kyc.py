from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from apps.kyc.models import (
    APPROVED, PENDING, PENDING_SECOND_REVIEW, REJECTED, InvalidTransition, KycCase, KycError,
    decide,
)
from core.approvals import ApprovalRequest
from core.audit import AuditEntry
from core.permissions import PermissionDenied


def make_case(db, watchlist_hit=False, status=PENDING):
    now = datetime.now(timezone.utc)
    case = KycCase(
        applicant_name="Test Applicant", date_of_birth=date(1990, 1, 1), ssn="900-00-0001",
        address="1 Test St", id_document_type="Passport", document_check_passed=True,
        identity_match_passed=True, watchlist_hit=watchlist_hit, status=status,
        created_at=now, updated_at=now,
    )
    db.add(case)
    db.commit()
    return case


def kyc_audit(db, case):
    return list(db.scalars(
        select(AuditEntry).where(AuditEntry.entity_type == "kyc_case",
                                 AuditEntry.entity_id == str(case.id)).order_by(AuditEntry.id)
    ))


def submit_watchlist_case(db, analyst, decision=APPROVED):
    case = make_case(db, watchlist_hit=True)
    decide(db, analyst, case, decision, "Watchlist hit is a name-only match")
    db.commit()
    assert case.status == PENDING_SECOND_REVIEW
    return case


def test_analyst_without_second_review_cannot_decide_pending_second_review(db, create_user):
    alice = create_user("alice", ["kyc_analyst"])
    carol = create_user("carol", ["kyc_analyst"])
    case = submit_watchlist_case(db, alice)

    with pytest.raises(PermissionDenied):
        decide(db, carol, case, APPROVED, "Looks fine")
    db.rollback()
    assert db.get(KycCase, case.id).status == PENDING_SECOND_REVIEW


def test_same_user_cannot_submit_and_second_review(db, create_user):
    bob = create_user("bob", ["kyc_senior_analyst"])
    case = submit_watchlist_case(db, bob)

    with pytest.raises(PermissionDenied):
        decide(db, bob, case, APPROVED, "Approving my own submission")
    db.rollback()
    assert db.get(KycCase, case.id).status == PENDING_SECOND_REVIEW


def test_second_reviewer_decides_watchlist_case(db, create_user):
    alice = create_user("alice", ["kyc_analyst"])
    bob = create_user("bob", ["kyc_senior_analyst"])
    case = submit_watchlist_case(db, alice, decision=APPROVED)

    decide(db, bob, case, REJECTED, "Watchlist hit confirmed")
    db.commit()
    assert case.status == REJECTED
    assert db.get(ApprovalRequest, case.approval_id).status == "REJECTED"


def test_non_watchlist_case_is_approved_directly_by_analyst(db, create_user):
    alice = create_user("alice", ["kyc_analyst"])
    case = make_case(db, watchlist_hit=False)

    decide(db, alice, case, APPROVED, "All checks passed")
    db.commit()
    assert case.status == APPROVED
    assert case.approval_id is None
    assert db.scalars(select(ApprovalRequest)).first() is None


def test_every_decision_creates_an_audit_entry(db, create_user):
    alice = create_user("alice", ["kyc_analyst"])
    bob = create_user("bob", ["kyc_senior_analyst"])
    direct = make_case(db)
    decide(db, alice, direct, REJECTED, "Document check failed on review")
    db.commit()
    watchlist = submit_watchlist_case(db, alice)
    decide(db, bob, watchlist, APPROVED, "False positive")
    db.commit()

    [entry] = kyc_audit(db, direct)
    assert (entry.actor_id, entry.action, entry.reason) == (
        alice.id, "kyc.case.decided", "Document check failed on review")
    assert entry.before["status"] == PENDING and entry.after["status"] == REJECTED

    submitted, reviewed = kyc_audit(db, watchlist)
    assert submitted.action == "kyc.case.submitted_for_second_review"
    assert submitted.before["status"] == PENDING
    assert submitted.after["status"] == PENDING_SECOND_REVIEW
    assert reviewed.actor_id == bob.id and reviewed.reason == "False positive"
    assert reviewed.before["status"] == PENDING_SECOND_REVIEW
    assert reviewed.after["status"] == APPROVED


@pytest.mark.parametrize("status", [APPROVED, REJECTED])
def test_illegal_status_transition_raises(db, create_user, status):
    bob = create_user("bob", ["kyc_senior_analyst"])
    case = make_case(db, status=status)

    with pytest.raises(InvalidTransition):
        decide(db, bob, case, APPROVED, "Re-deciding a closed case")
    assert kyc_audit(db, case) == []


def test_decision_requires_reason(db, create_user):
    alice = create_user("alice", ["kyc_analyst"])
    case = make_case(db)

    with pytest.raises(KycError):
        decide(db, alice, case, APPROVED, "   ")
    assert case.status == PENDING


def test_watchlist_flow_through_routes(client, db, create_user):
    create_user("alice", ["kyc_analyst"])
    create_user("bob", ["kyc_senior_analyst"])
    case = make_case(db, watchlist_hit=True)
    url = f"/kyc/cases/{case.id}/decide"

    def as_user(username):
        client.cookies.clear()
        r = client.post("/login", data={"username": username, "password": "test-password"})
        assert r.status_code == 303

    as_user("alice")
    assert client.post(url, data={"decision": "APPROVED", "reason": " "}).status_code == 400
    assert client.post(url, data={"decision": "APPROVED", "reason": "Name-only match"}).status_code == 303
    assert "Awaiting second review" not in client.get("/kyc").text
    assert client.post(url, data={"decision": "APPROVED", "reason": "Self review"}).status_code == 403

    as_user("bob")
    assert "Awaiting second review" in client.get("/kyc").text
    assert client.post(url, data={"decision": "APPROVED", "reason": "False positive"}).status_code == 303
    db.expire_all()
    assert db.get(KycCase, case.id).status == APPROVED
    assert client.post(url, data={"decision": "REJECTED", "reason": "Again"}).status_code == 400
