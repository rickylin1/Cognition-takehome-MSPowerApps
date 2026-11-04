"""Uses a test-only route and permissions so the platform is tested with no apps installed."""

import pytest
from fastapi import APIRouter, Depends

from config import roles
from core.permissions import require_permission
from main import app

WIDGET_VIEW = "test:widget.view"
GADGET_VIEW = "test:gadget.view"

widget_router = APIRouter()


@widget_router.get("/_test/widgets")
def widgets(user=Depends(require_permission(WIDGET_VIEW))):
    return {"ok": True}


@widget_router.get("/_test/gadgets")
def gadgets(user=Depends(require_permission(GADGET_VIEW))):
    return {"ok": True}


app.include_router(widget_router)


@pytest.fixture(autouse=True)
def test_roles(monkeypatch):
    monkeypatch.setitem(roles.ROLES, "widget_viewer", [WIDGET_VIEW])
    monkeypatch.setitem(roles.ROLES, "gadget_viewer", [GADGET_VIEW])


def test_user_without_permission_gets_403(client, login_as):
    login_as("tester", ["gadget_viewer"])
    assert client.get("/_test/widgets").status_code == 403


def test_user_with_no_roles_is_denied(client, login_as):
    login_as("tester")
    assert client.get("/_test/widgets").status_code == 403
    assert client.get("/_test/gadgets").status_code == 403


def test_two_roles_grant_union_of_permissions(client, login_as):
    login_as("tester", ["widget_viewer", "gadget_viewer"])
    assert client.get("/_test/widgets").status_code == 200
    assert client.get("/_test/gadgets").status_code == 200
