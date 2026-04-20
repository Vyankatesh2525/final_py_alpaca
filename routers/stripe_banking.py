# routers/stripe_banking.py — Stripe Financial Connections (bank linking, balances, transactions)
#
# Caching strategy: stale-while-revalidate
# ─────────────────────────────────────────
#  GET /balances (no force):
#    • Returns the cached value immediately (fast path).
#    • If the cache is older than BALANCE_CACHE_TTL_SECONDS, a background task
#      fires a Stripe refresh.  The next request (a few seconds later) will see
#      fresh data.
#
#  GET /balances?force=true:
#    • Synchronous: triggers the Stripe refresh and waits (up to ~10 s).
#    • Used right after bank linking to warm the cache before the user lands on
#      the Dashboard.
#
#  POST /webhook:
#    • Receives push events from Stripe (balance/transaction refreshed,
#      account disconnected) and immediately invalidates the affected user's
#      cache so the next regular fetch returns current data.

import json
import logging
import time
from datetime import datetime
from typing import List
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError

import stripe
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_models import User
from auth_utils import get_current_user_id
from config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
from database import get_db, SessionLocal

stripe.api_key = STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stripe", tags=["stripe_banking"])

# Cache TTLs (seconds).
# Background refresh fires when the cache is older than these values.
BALANCE_TTL      = 600   # 10 minutes
TRANSACTION_TTL  = 900   # 15 minutes


# ── DTOs ──────────────────────────────────────────────────────────────────────

class SaveAccountsRequest(BaseModel):
    sessionId: str
    accountIds: List[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _balance_cache_fresh(user: User) -> bool:
    if not user.stripe_data_synced_at:
        return False
    return (datetime.utcnow() - user.stripe_data_synced_at).total_seconds() < BALANCE_TTL


def _transaction_cache_fresh(user: User) -> bool:
    if not user.stripe_data_synced_at:
        return False
    return (datetime.utcnow() - user.stripe_data_synced_at).total_seconds() < TRANSACTION_TTL


def _stripe_get(path: str) -> dict:
    req = UrlRequest(
        f"https://api.stripe.com/v1{path}",
        headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}"},
    )
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _stripe_post(path: str, body: bytes) -> dict:
    req = UrlRequest(
        f"https://api.stripe.com/v1{path}",
        data=body,
        headers={
            "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except HTTPError:
        return {}


def _get_or_create_stripe_customer(user: User, db: Session) -> str:
    if user.stripe_customer_id:
        try:
            stripe.Customer.retrieve(user.stripe_customer_id)
            return user.stripe_customer_id
        except stripe.error.InvalidRequestError as e:
            if e.code != "resource_missing":
                raise

    customer = stripe.Customer.create(
        email=user.email or "",
        name=user.full_name or user.username,
        metadata={"username": user.username},
    )
    user.stripe_customer_id = customer.id
    db.commit()
    return customer.id


def _fetch_balances(account_ids: List[str]) -> list:
    """Pull live balances from Stripe for the given account IDs.
    Triggers a Stripe on-demand refresh and polls up to 10 s for completion."""
    results = []
    for account_id in account_ids:
        try:
            _stripe_post(
                f"/financial_connections/accounts/{account_id}/refresh",
                b"features[]=balance",
            )
            acct = {}
            for attempt in range(10):
                acct = _stripe_get(f"/financial_connections/accounts/{account_id}")
                if acct.get("balance_refresh", {}).get("status") != "pending":
                    break
                if attempt < 9:
                    time.sleep(1)

            balance_node = acct.get("balance") or {}
            balance_type = balance_node.get("type", "cash")
            if balance_type == "credit":
                avail = (balance_node.get("credit") or {}).get("used", {}).get("usd", 0)
            else:
                avail = (balance_node.get("cash") or {}).get("available", {}).get("usd", 0)

            results.append({
                "accountId":   acct.get("id"),
                "bankName":    acct.get("institution_name", "Unknown Bank"),
                "last4":       acct.get("last4", ""),
                "category":    acct.get("category", ""),
                "subcategory": acct.get("subcategory", ""),
                "available":   avail,
                "current":     avail,
                "currency":    "usd",
            })
        except Exception:
            logger.exception("Failed to fetch balance for account %s", account_id)
    return results


def _fetch_transactions(account_ids: List[str]) -> list:
    """Pull recent transactions from Stripe for the given account IDs.
    Triggers an on-demand refresh and polls up to 10 s for completion,
    matching the same pattern used for balance refreshes."""
    results = []
    for account_id in account_ids:
        try:
            try:
                _stripe_post(
                    f"/financial_connections/accounts/{account_id}/refresh",
                    b"features[]=transactions",
                )
            except Exception:
                pass  # non-fatal; list whatever Stripe has cached

            # Poll until transaction_refresh.status leaves "pending" (max 10 s)
            for attempt in range(10):
                acct = _stripe_get(f"/financial_connections/accounts/{account_id}")
                if acct.get("transaction_refresh", {}).get("status") != "pending":
                    break
                if attempt < 9:
                    time.sleep(1)

            data = _stripe_get(
                f"/financial_connections/transactions?account={account_id}&limit=100"
            )
            for tx in data.get("data", []):
                results.append({
                    "id":          tx.get("id"),
                    "accountId":   tx.get("account"),
                    "amount":      tx.get("amount", 0),
                    "currency":    tx.get("currency", "usd"),
                    "description": tx.get("description", ""),
                    "category":    tx.get("category", "other_expenses"),
                    "date":        tx.get("transacted_at", 0),
                })
        except HTTPError as e:
            if e.code == 400:
                logger.warning("Transactions not available for account %s (HTTP 400)", account_id)
            else:
                logger.exception("Failed to fetch transactions for account %s", account_id)
        except Exception:
            logger.exception("Failed to fetch transactions for account %s", account_id)
    return results


# ── Background refresh tasks (each creates its own DB session) ────────────────

def _refresh_balances_bg(user_id: int) -> None:
    """Background task: fetch fresh balances from Stripe, update the cache."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return
        account_ids = [a for a in (user.stripe_account_ids or "").split(",") if a]
        if not account_ids:
            return
        results = _fetch_balances(account_ids)
        user.stripe_balance_cache  = json.dumps(results)
        user.stripe_data_synced_at = datetime.utcnow()
        db.commit()
        logger.debug("Background balance refresh done for user_id=%s", user_id)
    except Exception:
        logger.exception("Background balance refresh failed for user_id=%s", user_id)
    finally:
        db.close()


def _refresh_transactions_bg(user_id: int) -> None:
    """Background task: fetch fresh transactions from Stripe, update the cache."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return
        account_ids = [a for a in (user.stripe_account_ids or "").split(",") if a]
        if not account_ids:
            return
        results = _fetch_transactions(account_ids)
        user.stripe_transactions_cache = json.dumps(results)
        user.stripe_data_synced_at     = datetime.utcnow()
        db.commit()
        logger.debug("Background transaction refresh done for user_id=%s", user_id)
    except Exception:
        logger.exception("Background transaction refresh failed for user_id=%s", user_id)
    finally:
        db.close()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/create-financial-connections-session")
def create_session(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_user(user_id, db)
    try:
        customer_id = _get_or_create_stripe_customer(user, db)
        session = stripe.financial_connections.Session.create(
            account_holder={"type": "customer", "customer": customer_id},
            permissions=["balances", "transactions"],
            prefetch=["balances"],
        )
        return {"client_secret": session.client_secret}
    except Exception as e:
        logger.exception("Failed to create Financial Connections session")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-accounts")
def save_accounts(
    body: SaveAccountsRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_user(user_id, db)
    try:
        user.stripe_account_ids         = ",".join(body.accountIds)
        user.stripe_balance_cache       = None
        user.stripe_transactions_cache  = None
        user.stripe_data_synced_at      = None
        db.commit()

        for account_id in body.accountIds:
            try:
                _stripe_post(
                    f"/financial_connections/accounts/{account_id}/subscribe",
                    b"features[]=transactions",
                )
            except Exception:
                logger.warning("Could not subscribe account %s to transactions", account_id)

        return {"status": "ok"}
    except Exception as e:
        logger.exception("Failed to save accounts")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def get_status(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_user(user_id, db)
    return {"connected": bool(user.stripe_account_ids)}


@router.get("/balances")
def get_balances(
    force: bool = False,
    background_tasks: BackgroundTasks = None,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_user(user_id, db)
    account_ids = [a for a in (user.stripe_account_ids or "").split(",") if a]
    if not account_ids:
        return []

    if force:
        # Synchronous path: caller is explicitly waiting for fresh data.
        # Used right after bank linking so the first Dashboard load is instant.
        results = _fetch_balances(account_ids)
        user.stripe_balance_cache  = json.dumps(results)
        user.stripe_data_synced_at = datetime.utcnow()
        db.commit()
        return results

    # Stale-while-revalidate: return the cache immediately; if it's stale,
    # kick off a background refresh so the *next* request gets fresh data.
    if not _balance_cache_fresh(user):
        background_tasks.add_task(_refresh_balances_bg, user_id)

    if user.stripe_balance_cache:
        try:
            return json.loads(user.stripe_balance_cache)
        except Exception:
            pass
    return []


@router.get("/transactions")
def get_transactions(
    force: bool = False,
    background_tasks: BackgroundTasks = None,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_user(user_id, db)
    account_ids = [a for a in (user.stripe_account_ids or "").split(",") if a]
    if not account_ids:
        return []

    if force:
        results = _fetch_transactions(account_ids)
        user.stripe_transactions_cache = json.dumps(results)
        user.stripe_data_synced_at     = datetime.utcnow()
        db.commit()
        return results

    if not _transaction_cache_fresh(user):
        background_tasks.add_task(_refresh_transactions_bg, user_id)

    if user.stripe_transactions_cache:
        try:
            return json.loads(user.stripe_transactions_cache)
        except Exception:
            pass
    return []


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receives Stripe push events and invalidates the relevant user's cache so
    the next regular /balances or /transactions request returns current data.

    Register this URL in the Stripe dashboard → Developers → Webhooks:
      https://yourdomain.com/api/stripe/webhook

    Events to enable:
      financial_connections.account.refreshed.balance
      financial_connections.account.refreshed.transactions
      financial_connections.account.disconnected
    """
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
    else:
        # Webhook secret not configured (dev environment) — parse without verification.
        logger.warning("STRIPE_WEBHOOK_SECRET not set; skipping signature verification")
        try:
            event = json.loads(payload)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = event.get("type", "")
    account_id = (event.get("data", {}).get("object", {}) or {}).get("id")

    if not account_id:
        return {"status": "ignored"}

    if event_type in (
        "financial_connections.account.refreshed.balance",
        "financial_connections.account.disconnected",
    ):
        # Invalidate the balance cache for whichever user owns this account.
        user = (
            db.query(User)
            .filter(User.stripe_account_ids.like(f"%{account_id}%"))
            .first()
        )
        if user:
            user.stripe_data_synced_at = None
            db.commit()
            logger.info("Invalidated balance cache for user_id=%s via webhook %s", user.id, event_type)

    elif event_type == "financial_connections.account.refreshed.transactions":
        user = (
            db.query(User)
            .filter(User.stripe_account_ids.like(f"%{account_id}%"))
            .first()
        )
        if user:
            user.stripe_transactions_cache = None
            user.stripe_data_synced_at     = None
            db.commit()
            logger.info("Invalidated transaction cache for user_id=%s via webhook", user.id)

    return {"status": "ok"}
