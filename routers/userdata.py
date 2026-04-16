# routers/userdata.py — synced app-state: points, AI message count, Plaid token
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_models import User
from auth_utils import get_current_user_id
from database import get_db

router = APIRouter(prefix="/api/userdata", tags=["userdata"])


# ── DTOs ──────────────────────────────────────────────────────────────────────

class UserDataResponse(BaseModel):
    learnPoints: int
    cardPoints: int
    aiMessageCount: int
    aiWeekStart: Optional[int]
    isAdmin: bool
    isSubscribed: bool


class PointsRequest(BaseModel):
    learnPoints: int
    cardPoints: int


class AiMessageRequest(BaseModel):
    count: int
    weekStart: int


class PlaidTokenRequest(BaseModel):
    token: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_own_user(username: str, user_id: int, db: Session) -> User:
    """Look up user by username and verify the JWT belongs to that user."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{username}", response_model=UserDataResponse)
def get_user_data(
    username: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_own_user(username, user_id, db)
    return UserDataResponse(
        learnPoints=user.learn_points,
        cardPoints=user.card_points,
        aiMessageCount=user.ai_message_count,
        aiWeekStart=user.ai_week_start,
        isAdmin=bool(user.is_admin),
        isSubscribed=bool(user.subscribed),
    )


@router.put("/{username}/points")
def update_points(
    username: str,
    body: PointsRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_own_user(username, user_id, db)
    user.learn_points = body.learnPoints
    user.card_points  = body.cardPoints
    db.commit()
    return {"status": "ok"}


@router.post("/{username}/ai-message")
def update_ai_message(
    username: str,
    body: AiMessageRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_own_user(username, user_id, db)
    user.ai_message_count = body.count
    user.ai_week_start    = body.weekStart
    db.commit()
    return {"aiMessageCount": user.ai_message_count}


@router.post("/{username}/plaid-token")
def save_plaid_token(
    username: str,
    body: PlaidTokenRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_own_user(username, user_id, db)
    user.plaid_access_token = body.token
    db.commit()
    return {"status": "ok"}


@router.get("/{username}/plaid-token")
def get_plaid_token(
    username: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_own_user(username, user_id, db)
    return {"token": user.plaid_access_token}


@router.delete("/{username}/plaid-token")
def clear_plaid_token(
    username: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = _get_own_user(username, user_id, db)
    user.plaid_access_token = None
    db.commit()
    return {"status": "ok"}
