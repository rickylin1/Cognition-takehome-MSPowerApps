import inspect

from sqlalchemy import func, select

from core import audit
from core.audit import AuditEntry


def test_audit_module_exposes_no_update_or_delete():
    public_functions = {
        name for name, obj in inspect.getmembers(audit, inspect.isfunction)
        if obj.__module__ == audit.__name__ and not name.startswith("_")
    }
    assert public_functions == {"log", "list_entries"}
    forbidden = ("update", "delete", "remove", "edit", "modify", "clear", "purge")
    assert not [n for n in dir(audit) if any(word in n.lower() for word in forbidden)]


def test_entries_can_only_be_added(db, create_user):
    actor = create_user("tester")
    audit.log(db, actor, "thing.created", "thing", 1, after={"v": 1})
    audit.log(db, actor, "thing.changed", "thing", 1, before={"v": 1}, after={"v": 2}, reason="fix")
    db.commit()

    assert db.scalar(select(func.count()).select_from(AuditEntry)) == 2
    newest = audit.list_entries(db)[0]
    assert (newest.action, newest.before, newest.after, newest.reason) == (
        "thing.changed", {"v": 1}, {"v": 2}, "fix"
    )
    assert newest.actor_id == actor.id


def test_audit_page_lists_entries_for_auditor(client, login_as):
    login_as("tester", ["auditor"])
    response = client.get("/audit")
    assert response.status_code == 200
    assert "auth.login_succeeded" in response.text
