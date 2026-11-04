from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.kyc.models import PENDING_SECOND_REVIEW, KycCase, KycError, decide
from apps.kyc.permissions import CASE_DECIDE, CASE_SECOND_REVIEW, CASE_VIEW
from core.approvals import ApprovalRequest
from core.auth import User
from core.db import get_db
from core.permissions import has_permission, require_permission
from core.registry import register_tool

templates = Jinja2Templates(
    directory=[Path(__file__).parent / "templates", Path(__file__).parents[2] / "core" / "templates"]
)
router = APIRouter(prefix="/kyc")

register_tool("KYC review queue", "/kyc", CASE_VIEW)


def _get_case(db: Session, case_id: int) -> KycCase:
    case = db.get(KycCase, case_id)
    if case is None:
        raise HTTPException(status_code=404)
    return case


def _render_case(request, db, user, case, error=None, status_code=200):
    approval = db.get(ApprovalRequest, case.approval_id) if case.approval_id else None
    return templates.TemplateResponse(
        request, "case.html",
        {"user": user, "case": case, "approval": approval, "error": error,
         "can_second_review": has_permission(user, CASE_SECOND_REVIEW)},
        status_code=status_code,
    )


@router.get("")
def queue(
    request: Request,
    user: User = Depends(require_permission(CASE_VIEW)),
    db: Session = Depends(get_db),
):
    cases = list(db.scalars(select(KycCase).order_by(KycCase.id)))
    awaiting = None
    if has_permission(user, CASE_SECOND_REVIEW):
        awaiting = [c for c in cases if c.status == PENDING_SECOND_REVIEW]
    return templates.TemplateResponse(
        request, "queue.html", {"user": user, "cases": cases, "awaiting": awaiting}
    )


@router.get("/cases/{case_id}")
def case_detail(
    request: Request,
    case_id: int,
    user: User = Depends(require_permission(CASE_VIEW)),
    db: Session = Depends(get_db),
):
    return _render_case(request, db, user, _get_case(db, case_id))


@router.post("/cases/{case_id}/decide")
def decide_case(
    request: Request,
    case_id: int,
    decision: str = Form(...),
    reason: str = Form(""),
    user: User = Depends(require_permission(CASE_DECIDE)),
    db: Session = Depends(get_db),
):
    case = _get_case(db, case_id)
    try:
        decide(db, user, case, decision, reason)
    except KycError as exc:
        db.rollback()
        return _render_case(request, db, user, case, error=str(exc), status_code=400)
    db.commit()
    return RedirectResponse(f"/kyc/cases/{case_id}", status_code=303)
