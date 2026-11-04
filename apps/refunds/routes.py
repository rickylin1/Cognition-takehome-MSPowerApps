from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.refunds.models import (
    PENDING_APPROVAL, Refund, RefundError, Transaction, decide_refund, parse_amount,
    refundable_cents, refunds_for, request_refund, threshold_cents,
)
from apps.refunds.permissions import REFUND_APPROVE, REFUND_REQUEST, TRANSACTION_VIEW
from core.auth import User
from core.db import get_db
from core.permissions import has_permission, require_permission
from core.registry import register_tool

templates = Jinja2Templates(
    directory=[Path(__file__).parent / "templates", Path(__file__).parents[2] / "core" / "templates"]
)
templates.env.filters["usd"] = lambda cents: f"${cents / 100:,.2f}"
router = APIRouter(prefix="/refunds")

register_tool("Refunds dashboard", "/refunds", TRANSACTION_VIEW)


def _get_transaction(db: Session, transaction_id: int) -> Transaction:
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404)
    return transaction


def _get_refund(db: Session, refund_id: int) -> Refund:
    refund = db.get(Refund, refund_id)
    if refund is None:
        raise HTTPException(status_code=404)
    return refund


def _pending(db: Session) -> list[tuple[Refund, Transaction]]:
    rows = db.execute(
        select(Refund, Transaction).join(Transaction, Refund.transaction_id == Transaction.id)
        .where(Refund.status == PENDING_APPROVAL).order_by(Refund.id)
    )
    return [tuple(r) for r in rows]


def _render_transaction(request, db, user, transaction, error=None, status_code=200):
    return templates.TemplateResponse(
        request, "transaction.html",
        {"user": user, "tx": transaction, "refunds": refunds_for(db, transaction),
         "refundable": refundable_cents(db, transaction), "threshold": threshold_cents(),
         "can_request": has_permission(user, REFUND_REQUEST),
         "can_approve": has_permission(user, REFUND_APPROVE), "error": error},
        status_code=status_code,
    )


def _render_approvals(request, db, user, error=None, status_code=200):
    return templates.TemplateResponse(
        request, "approvals.html",
        {"user": user, "pending": _pending(db), "error": error}, status_code=status_code,
    )


@router.get("")
def transactions(
    request: Request,
    user: User = Depends(require_permission(TRANSACTION_VIEW)),
    db: Session = Depends(get_db),
):
    txs = list(db.scalars(select(Transaction).order_by(Transaction.id)))
    pending_count = len(_pending(db)) if has_permission(user, REFUND_APPROVE) else None
    return templates.TemplateResponse(
        request, "transactions.html",
        {"user": user, "transactions": txs, "pending_count": pending_count},
    )


@router.get("/transactions/{transaction_id}")
def transaction_detail(
    request: Request,
    transaction_id: int,
    user: User = Depends(require_permission(TRANSACTION_VIEW)),
    db: Session = Depends(get_db),
):
    return _render_transaction(request, db, user, _get_transaction(db, transaction_id))


@router.post("/transactions/{transaction_id}/refunds")
def create_refund(
    request: Request,
    transaction_id: int,
    amount: str = Form(""),
    reason: str = Form(""),
    user: User = Depends(require_permission(REFUND_REQUEST)),
    db: Session = Depends(get_db),
):
    transaction = _get_transaction(db, transaction_id)
    try:
        request_refund(db, user, transaction, parse_amount(amount), reason)
    except RefundError as exc:
        db.rollback()
        return _render_transaction(request, db, user, transaction, error=str(exc), status_code=400)
    db.commit()
    return RedirectResponse(f"/refunds/transactions/{transaction_id}", status_code=303)


@router.get("/approvals")
def pending_approvals(
    request: Request,
    user: User = Depends(require_permission(REFUND_APPROVE)),
    db: Session = Depends(get_db),
):
    return _render_approvals(request, db, user)


@router.post("/refunds/{refund_id}/decide")
def decide(
    request: Request,
    refund_id: int,
    decision: str = Form(...),
    reason: str = Form(""),
    user: User = Depends(require_permission(REFUND_APPROVE)),
    db: Session = Depends(get_db),
):
    refund = _get_refund(db, refund_id)
    try:
        decide_refund(db, user, refund, decision, reason)
    except RefundError as exc:
        db.rollback()
        return _render_approvals(request, db, user, error=str(exc), status_code=400)
    db.commit()
    return RedirectResponse("/refunds/approvals", status_code=303)
