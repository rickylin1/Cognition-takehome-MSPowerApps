import pytest
from sqlalchemy import select

from config import roles
from core import approvals
from core.audit import AuditEntry
from core.permissions import PermissionDenied

APPROVE = "test:widget.approve"


@pytest.fixture(autouse=True)
def test_roles(monkeypatch):
    monkeypatch.setitem(roles.ROLES, "widget_approver", [APPROVE])
    monkeypatch.setitem(roles.ROLES, "widget_requester", [])


def _request(db, actor):
    req = approvals.request(db, actor, "widget.change", "widget", 1, {"v": 2}, APPROVE)
    db.commit()
    return req


def test_requester_cannot_approve_own_request(db, create_user):
    requester = create_user("requester", ["widget_approver"])
    req = _request(db, requester)

    with pytest.raises(PermissionDenied):
        approvals.decide(db, requester, req.id, approvals.APPROVED, "self")
    db.rollback()
    assert db.get(approvals.ApprovalRequest, req.id).status == approvals.PENDING


def test_user_without_approver_permission_cannot_decide(db, create_user):
    requester = create_user("requester", ["widget_requester"])
    other = create_user("other", ["widget_requester"])
    req = _request(db, requester)

    with pytest.raises(PermissionDenied):
        approvals.decide(db, other, req.id, approvals.REJECTED, "no")
    db.rollback()
    assert db.get(approvals.ApprovalRequest, req.id).status == approvals.PENDING


def test_different_approver_decides_and_everything_is_audited(db, create_user):
    requester = create_user("requester", ["widget_requester"])
    approver = create_user("approver", ["widget_approver"])
    req = _request(db, requester)

    decided = approvals.decide(db, approver, req.id, approvals.APPROVED, "looks good")
    db.commit()

    assert decided.status == approvals.APPROVED
    assert decided.decided_by_id == approver.id
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(db, approver, req.id, approvals.REJECTED, "again")

    entries = db.scalars(select(AuditEntry).order_by(AuditEntry.id)).all()
    assert [(e.action, e.actor_id) for e in entries] == [
        ("approval.requested", requester.id),
        ("approval.approved", approver.id),
    ]
    assert entries[1].reason == "looks good"
