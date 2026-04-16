# routers/goals.py — user goals and sub-tasks
import json
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_models import User, UserGoal
from database import get_db

router = APIRouter(prefix="/api/goals", tags=["goals"])


# ── DTOs ──────────────────────────────────────────────────────────────────────

class SubTaskDto(BaseModel):
    id: str
    title: str
    isCompleted: bool = False


class GoalDto(BaseModel):
    id: str
    title: str
    createdAt: int
    subTasks: List[SubTaskDto]


class CreateGoalRequest(BaseModel):
    id: str
    title: str
    createdAt: int = 0   # 0 → filled with current epoch-ms below


class UpdateSubTasksRequest(BaseModel):
    subTasks: List[SubTaskDto]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_user(username: str, db: Session) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _goal_to_dto(goal: UserGoal) -> GoalDto:
    try:
        tasks = [SubTaskDto(**t) for t in json.loads(goal.sub_tasks)]
    except Exception:
        tasks = []
    return GoalDto(id=goal.id, title=goal.title, createdAt=goal.created_at, subTasks=tasks)


def _now_ms() -> int:
    return int(time.time() * 1000)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{username}", response_model=List[GoalDto])
def get_goals(username: str, db: Session = Depends(get_db)):
    user = _resolve_user(username, db)
    goals = db.query(UserGoal).filter(UserGoal.user_id == user.id).all()
    return [_goal_to_dto(g) for g in goals]


@router.post("/{username}", response_model=GoalDto)
def create_goal(username: str, body: CreateGoalRequest, db: Session = Depends(get_db)):
    user = _resolve_user(username, db)
    ts = body.createdAt or _now_ms()

    # Upsert — if the goal already exists (same UUID), update it
    goal = db.query(UserGoal).filter(UserGoal.id == body.id).first()
    if goal:
        goal.title      = body.title
        goal.created_at = ts
    else:
        goal = UserGoal(id=body.id, user_id=user.id, title=body.title, created_at=ts)
        db.add(goal)

    db.commit()
    db.refresh(goal)
    return _goal_to_dto(goal)


@router.put("/{username}/{goal_id}/subtasks", response_model=GoalDto)
def update_sub_tasks(
    username: str,
    goal_id: str,
    body: UpdateSubTasksRequest,
    db: Session = Depends(get_db),
):
    user = _resolve_user(username, db)
    goal = db.query(UserGoal).filter(UserGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    goal.sub_tasks = json.dumps([t.model_dump() for t in body.subTasks])
    db.commit()
    return _goal_to_dto(goal)


@router.post("/{username}/{goal_id}/subtask/{subtask_id}/toggle", response_model=GoalDto)
def toggle_sub_task(
    username: str,
    goal_id: str,
    subtask_id: str,
    db: Session = Depends(get_db),
):
    user = _resolve_user(username, db)
    goal = db.query(UserGoal).filter(UserGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        tasks = json.loads(goal.sub_tasks)
    except Exception:
        tasks = []

    toggled = [
        {**t, "isCompleted": not t.get("isCompleted", False)} if t.get("id") == subtask_id else t
        for t in tasks
    ]
    goal.sub_tasks = json.dumps(toggled)
    db.commit()
    return _goal_to_dto(goal)


@router.delete("/{username}/{goal_id}")
def delete_goal(username: str, goal_id: str, db: Session = Depends(get_db)):
    user = _resolve_user(username, db)
    goal = db.query(UserGoal).filter(UserGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    db.delete(goal)
    db.commit()
    return {"status": "deleted"}


@router.put("/{username}/sync", response_model=List[GoalDto])
def sync_goals(username: str, body: List[CreateGoalRequest], db: Session = Depends(get_db)):
    """Bulk-replace all goals — used after login / reinstall to push device state."""
    user = _resolve_user(username, db)
    incoming_ids = {g.id for g in body}

    # Delete goals no longer on the device
    existing = db.query(UserGoal).filter(UserGoal.user_id == user.id).all()
    for g in existing:
        if g.id not in incoming_ids:
            db.delete(g)

    # Upsert incoming goals
    saved = []
    for req in body:
        ts   = req.createdAt or _now_ms()
        goal = db.query(UserGoal).filter(UserGoal.id == req.id).first()
        if goal:
            goal.title      = req.title
            goal.created_at = ts
        else:
            goal = UserGoal(id=req.id, user_id=user.id, title=req.title, created_at=ts)
            db.add(goal)
        saved.append(goal)

    db.commit()
    for g in saved:
        db.refresh(g)
    return [_goal_to_dto(g) for g in saved]
