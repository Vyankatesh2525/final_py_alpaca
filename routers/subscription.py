# routers/subscription.py — premium subscription via Stripe PaymentIntent
import logging

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

router = APIRouter(prefix="/api/subscription", tags=["subscription"])

SUBSCRIPTION_PRICE_CENTS = 999   # $9.99


# ── DTOs ──────────────────────────────────────────────────────────────────────

class CreatePaymentIntentRequest(BaseModel):
    username: str


class VerifyRequest(BaseModel):
    username: str
    paymentIntentId: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user(username: str, db: Session) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    return user


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/create-payment-intent")
def create_payment_intent(
    body: CreatePaymentIntentRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        intent = stripe.PaymentIntent.create(
            amount=SUBSCRIPTION_PRICE_CENTS,
            currency="usd",
            metadata={"username": body.username},
            description="Clau Premium Subscription",
        )
        return {"clientSecret": intent.client_secret, "paymentIntentId": intent.id}
    except Exception as e:
        logger.exception("Failed to create subscription PaymentIntent")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify")
def verify_subscription(
    body: VerifyRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        intent = stripe.PaymentIntent.retrieve(body.paymentIntentId)
        if intent.status != "succeeded":
            raise HTTPException(status_code=400, detail="Payment not completed")

        user = _get_user(body.username, db)
        user.subscribed = True
        db.commit()
        return {"status": "success", "message": "Subscription activated", "subscribed": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to verify subscription")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{username}")
def get_subscription_status(username: str, db: Session = Depends(get_db)):
    user = _get_user(username, db)
    return {"status": "success", "subscribed": bool(user.subscribed)}


class CancelRequest(BaseModel):
    username: str


@router.post("/cancel")
def cancel_subscription(
    body: CancelRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_user(body.username, db)
    if user.id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user.subscribed = False
    db.commit()
    return {"status": "success", "message": "Subscription cancelled"}
