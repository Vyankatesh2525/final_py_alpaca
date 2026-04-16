# routers/stripe_banking.py — Stripe Financial Connections (bank linking, balances, transactions)
import json
import logging
import time
from datetime import datetime
from typing import List
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError

import stripe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_models import User
from auth_utils import get_current_user_id
from config import STRIPE_SECRET_KEY
from database import get_db

stripe.api_key = STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stripe", tags=["stripe_banking"])

CACHE_TTL_SECONDS = 3600   # 1 hour, matches Spring Boot


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


def _cache_fresh(user: User) -> bool:
    if not user.stripe_data_synced_at:
        return False
    age = (datetime.utcnow() - user.stripe_data_synced_at).total_seconds()
    return age < CACHE_TTL_SECONDS


def _stripe_get(path: str) -> dict:
    """Raw Stripe REST call returning parsed JSON."""
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

        # Subscribe each account to transaction data
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
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_user(user_id, db)

    # Return cache if fresh
    if not force and _cache_fresh(user) and user.stripe_balance_cache:
        try:
            return json.loads(user.stripe_balance_cache)
        except Exception:
            pass

    account_ids = [a for a in (user.stripe_account_ids or "").split(",") if a]
    if not account_ids:
        return []

    results = []
    for account_id in account_ids:
        try:
            # Trigger an on-demand balance refresh
            _stripe_post(
                f"/financial_connections/accounts/{account_id}/refresh",
                b"features[]=balance",
            )

            # Poll until balance_refresh.status != "pending" (max 10 s)
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

    user.stripe_balance_cache  = json.dumps(results)
    user.stripe_data_synced_at = datetime.utcnow()
    db.commit()
    return results


@router.get("/transactions")
def get_transactions(
    force: bool = False,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_user(user_id, db)

    # Return cache if fresh
    if not force and _cache_fresh(user) and user.stripe_transactions_cache:
        try:
            return json.loads(user.stripe_transactions_cache)
        except Exception:
            pass

    account_ids = [a for a in (user.stripe_account_ids or "").split(",") if a]
    if not account_ids:
        return []

    results = []
    for account_id in account_ids:
        try:
            # Trigger a transaction refresh so data is current
            try:
                _stripe_post(
                    f"/financial_connections/accounts/{account_id}/refresh",
                    b"features[]=transactions",
                )
            except Exception:
                pass  # non-fatal; proceed to list whatever Stripe has

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

    user.stripe_transactions_cache = json.dumps(results)
    user.stripe_data_synced_at     = datetime.utcnow()
    db.commit()
    return results
