from datetime import date

import pytest
from sqlalchemy import select

from apps.refunds.models import (
    ISSUED, PARTIALLY_REFUNDED, PENDING_APPROVAL, REFUNDED, REJECTED, ExceedsRefundable,
    InvalidAmount, NotPending, Refund, RefundError, Transaction, decide_refund, parse_amount,
    request_refund, threshold_cents,
)
from config import refunds as refunds_config
from core.approvals import ApprovalRequest
from core.audit import AuditEntry
from core.permissions import PermissionDenied


def make_tx(db, amount_cents=100000):
    tx = Transaction(customer_name="Test Customer", amount_cents=amount_cents,
                     date=date(2026, 10, 1), merchant="Test Merchant")
    db.add(tx)
    db.commit()
    return tx


def refund_actions(db, refund):
    return [e.action for e in db.scalars(
        select(AuditEntry).where(AuditEntry.entity_type == "refunds_refund",
                                 AuditEntry.entity_id == str(refund.id)).order_by(AuditEntry.id)
    )]


@pytest.fixture
def dana(create_user):
    return create_user("dana", ["support_agent"])


@pytest.fixture
def erin(create_user):
    return create_user("erin", ["support_lead"])


def test_threshold_is_500_dollars_from_config():
    assert refunds_config.APPROVAL_THRESHOLD == 500
    assert threshold_cents() == 50000


@pytest.mark.parametrize("cents", [1, 12345, 50000])
def test_refund_up_to_threshold_is_issued_immediately(db, dana, cents):
    tx = make_tx(db)
    refund = request_refund(db, dana, tx, cents, "Damaged item")
    db.commit()
    assert refund.status == ISSUED and refund.issued_at is not None
    assert refund.approval_id is None
    assert db.scalars(select(ApprovalRequest)).first() is None
    assert tx.status == PARTIALLY_REFUNDED


def test_refund_above_threshold_needs_approval(db, dana):
    tx = make_tx(db)
    refund = request_refund(db, dana, tx, 50001, "Order never arrived")
    db.commit()
    assert refund.status == PENDING_APPROVAL
    approval = db.get(ApprovalRequest, refund.approval_id)
    assert approval.status == "PENDING"
    assert approval.approver_permission == "refunds:refund.approve"
    assert tx.status == "SETTLED"


def test_refund_cannot_exceed_transaction_amount(db, dana):
    tx = make_tx(db, 30000)
    with pytest.raises(ExceedsRefundable):
        request_refund(db, dana, tx, 30001, "Too much")
    db.rollback()
    assert db.scalars(select(Refund)).first() is None


def test_refund_cannot_exceed_amount_minus_issued_refunds(db, dana):
    tx = make_tx(db, 30000)
    request_refund(db, dana, tx, 20000, "Partial")
    db.commit()
    with pytest.raises(ExceedsRefundable):
        request_refund(db, dana, tx, 10001, "Over the rest")
    db.rollback()
    request_refund(db, dana, tx, 10000, "The rest")
    db.commit()
    assert tx.status == REFUNDED


def test_approver_must_be_a_different_user(db, erin):
    tx = make_tx(db)
    refund = request_refund(db, erin, tx, 70000, "Large refund")
    db.commit()
    with pytest.raises(PermissionDenied):
        decide_refund(db, erin, refund, "APPROVED", "Approving my own")
    db.rollback()
    assert db.get(Refund, refund.id).status == PENDING_APPROVAL


def test_approver_needs_approve_permission(db, dana, create_user):
    other_agent = create_user("gina", ["support_agent"])
    tx = make_tx(db)
    refund = request_refund(db, dana, tx, 70000, "Large refund")
    db.commit()
    with pytest.raises(PermissionDenied):
        decide_refund(db, other_agent, refund, "APPROVED", "Looks fine")
    db.rollback()
    assert db.get(Refund, refund.id).status == PENDING_APPROVAL


def test_approval_issues_refund(db, dana, erin):
    tx = make_tx(db)
    refund = request_refund(db, dana, tx, 70000, "Large refund")
    db.commit()
    decide_refund(db, erin, refund, "APPROVED", "Verified with customer")
    db.commit()
    assert refund.status == ISSUED
    assert db.get(ApprovalRequest, refund.approval_id).status == "APPROVED"
    assert tx.status == PARTIALLY_REFUNDED


def test_rejection_does_not_issue_refund(db, dana, erin):
    tx = make_tx(db)
    refund = request_refund(db, dana, tx, 70000, "Large refund")
    db.commit()
    decide_refund(db, erin, refund, "REJECTED", "Outside refund policy")
    db.commit()
    assert refund.status == REJECTED and refund.issued_at is None
    assert db.get(ApprovalRequest, refund.approval_id).status == "REJECTED"
    assert tx.status == "SETTLED"
    with pytest.raises(NotPending):
        decide_refund(db, erin, refund, "APPROVED", "Changed my mind")


def test_approval_rechecks_refundable_amount(db, dana, erin):
    tx = make_tx(db, 100000)
    big = request_refund(db, dana, tx, 70000, "Large refund")
    request_refund(db, dana, tx, 40000, "Second refund")  # issued, leaves 600.00
    db.commit()
    with pytest.raises(ExceedsRefundable):
        decide_refund(db, erin, big, "APPROVED", "Verified")
    db.rollback()
    assert db.get(Refund, big.id).status == PENDING_APPROVAL


def test_every_refund_step_is_audited(db, dana, erin):
    tx = make_tx(db)
    small = request_refund(db, dana, tx, 1000, "Small")
    approved = request_refund(db, dana, tx, 60000, "Approve me")
    rejected = request_refund(db, dana, tx, 60000, "Reject me")
    db.commit()
    decide_refund(db, erin, approved, "APPROVED", "OK")
    decide_refund(db, erin, rejected, "REJECTED", "No")
    db.commit()

    assert refund_actions(db, small) == ["refunds.refund.requested", "refunds.refund.issued"]
    assert refund_actions(db, approved) == [
        "refunds.refund.requested", "refunds.refund.approved", "refunds.refund.issued"]
    assert refund_actions(db, rejected) == ["refunds.refund.requested", "refunds.refund.rejected"]
    issued = db.scalar(select(AuditEntry).where(
        AuditEntry.action == "refunds.refund.issued", AuditEntry.entity_id == str(approved.id)))
    assert issued.actor_id == erin.id
    assert issued.before["status"] == PENDING_APPROVAL and issued.after["status"] == ISSUED
    core_actions = [e.action for e in db.scalars(
        select(AuditEntry).where(AuditEntry.entity_type == "approval_request"))]
    assert core_actions.count("approval.requested") == 2
    assert {"approval.approved", "approval.rejected"} <= set(core_actions)


def test_reason_is_required(db, dana):
    tx = make_tx(db)
    with pytest.raises(RefundError):
        request_refund(db, dana, tx, 1000, "  ")


@pytest.mark.parametrize("text,cents", [("700", 70000), ("700.5", 70050), (" 0.01 ", 1)])
def test_parse_amount(text, cents):
    assert parse_amount(text) == cents


@pytest.mark.parametrize("text", ["", "abc", "0", "-5", "1.234", "NaN", "inf"])
def test_parse_amount_rejects_invalid(text):
    with pytest.raises(InvalidAmount):
        parse_amount(text)


def test_permissions_on_routes(client, db, login_as):
    tx = make_tx(db)
    assert client.get("/refunds").status_code == 303  # logged out -> /login
    login_as("nobody", [])
    for url in ["/refunds", f"/refunds/transactions/{tx.id}", "/refunds/approvals"]:
        assert client.get(url).status_code == 403
    assert client.post(f"/refunds/transactions/{tx.id}/refunds",
                       data={"amount": "1", "reason": "x"}).status_code == 403
    assert client.post("/refunds/refunds/1/decide",
                       data={"decision": "APPROVED", "reason": "x"}).status_code == 403
    assert "Refunds dashboard" not in client.get("/").text


def test_700_refund_flow_through_routes(client, db, dana, erin):
    tx = make_tx(db)

    def as_user(username):
        client.cookies.clear()
        r = client.post("/login", data={"username": username, "password": "test-password"})
        assert r.status_code == 303

    as_user("dana")
    assert "Refunds dashboard" in client.get("/").text
    assert client.get("/refunds/approvals").status_code == 403
    url = f"/refunds/transactions/{tx.id}/refunds"
    assert client.post(url, data={"amount": "5000", "reason": "Too much"}).status_code == 400
    assert client.post(url, data={"amount": "700", "reason": "Order never arrived"}).status_code == 303
    [refund] = db.scalars(select(Refund)).all()
    assert refund.status == PENDING_APPROVAL

    as_user("erin")
    assert "Order never arrived" in client.get("/refunds/approvals").text
    decide_url = f"/refunds/refunds/{refund.id}/decide"
    assert client.post(decide_url, data={"decision": "APPROVED", "reason": "Verified"}).status_code == 303
    db.expire_all()
    assert db.get(Refund, refund.id).status == ISSUED
    assert client.post(decide_url, data={"decision": "APPROVED", "reason": "Again"}).status_code == 400
