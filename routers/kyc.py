# routers/kyc.py — KYC submission and admin review
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_models import User, KYCSubmission
from auth_utils import get_current_user_id
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kyc", tags=["kyc"])


# ── DTOs ──────────────────────────────────────────────────────────────────────

class KYCSubmitRequest(BaseModel):
    userId: int
    fullName: str
    dateOfBirth: str          # MM/dd/yyyy
    idType: str
    idNumber: str
    address: str
    phone: str
    frontDocUrl: Optional[str] = None
    backDocUrl: Optional[str] = None


class KYCRejectRequest(BaseModel):
    reason: str
    adminName: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_dob(dob_str: str) -> date:
    try:
        return datetime.strptime(dob_str, "%m/%d/%Y").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {dob_str!r} — expected MM/dd/yyyy")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/submit")
def submit_kyc(body: KYCSubmitRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == body.userId).first()
    if not user:
        return {"status": "error", "message": "User not found"}, 400

    existing = db.query(KYCSubmission).filter(KYCSubmission.user_id == body.userId).first()
    if existing and existing.status == "pending":
        raise HTTPException(status_code=400, detail="KYC already submitted and pending review")

    dob = _parse_dob(body.dateOfBirth)

    if existing:
        existing.full_name        = body.fullName
        existing.date_of_birth    = dob
        existing.id_type          = body.idType
        existing.id_number        = body.idNumber
        existing.address          = body.address
        existing.phone            = body.phone
        existing.front_doc_url    = body.frontDocUrl
        existing.back_doc_url     = body.backDocUrl
        existing.status           = "pending"
        existing.rejection_reason = None
        existing.submitted_at     = datetime.utcnow()
        kyc = existing
    else:
        kyc = KYCSubmission(
            user_id       = body.userId,
            full_name     = body.fullName,
            date_of_birth = dob,
            id_type       = body.idType,
            id_number     = body.idNumber,
            address       = body.address,
            phone         = body.phone,
            front_doc_url = body.frontDocUrl,
            back_doc_url  = body.backDocUrl,
        )
        db.add(kyc)

    user.kyc_status = "pending"
    db.commit()
    db.refresh(kyc)
    return {"status": "success", "message": "KYC submitted successfully", "kycId": kyc.id}


@router.get("/status/{user_id}")
def get_kyc_status(user_id: int, db: Session = Depends(get_db)):
    kyc = db.query(KYCSubmission).filter(KYCSubmission.user_id == user_id).first()
    if not kyc:
        return {"status": "success", "kycStatus": "none", "message": "No KYC submission found"}
    return {
        "status":          "success",
        "kycStatus":       kyc.status,
        "rejectionReason": kyc.rejection_reason or "",
        "submittedAt":     kyc.submitted_at.isoformat(),
    }


@router.get("/details/{user_id}")
def get_kyc_details(user_id: int, db: Session = Depends(get_db)):
    kyc = db.query(KYCSubmission).filter(KYCSubmission.user_id == user_id).first()
    if not kyc:
        return {"status": "success", "kyc": {}, "message": "No KYC submission found"}
    return {
        "status": "success",
        "kyc": {
            "id":              kyc.id,
            "fullName":        kyc.full_name,
            "dateOfBirth":     kyc.date_of_birth.isoformat(),
            "idType":          kyc.id_type,
            "idNumber":        kyc.id_number,
            "address":         kyc.address,
            "phone":           kyc.phone,
            "frontDocUrl":     kyc.front_doc_url or "",
            "backDocUrl":      kyc.back_doc_url or "",
            "status":          kyc.status,
            "rejectionReason": kyc.rejection_reason or "",
            "submittedAt":     kyc.submitted_at.isoformat(),
        },
    }


# ── Admin endpoints ───────────────────────────────────────────────────────────

@router.get("/admin/pending")
def get_pending_kyc(db: Session = Depends(get_db)):
    kycs = db.query(KYCSubmission).filter(KYCSubmission.status == "pending").all()
    return {
        "status": "success",
        "count": len(kycs),
        "submissions": [
            {"id": k.id, "userId": k.user_id, "fullName": k.full_name,
             "idType": k.id_type, "status": k.status, "submittedAt": k.submitted_at.isoformat()}
            for k in kycs
        ],
    }


@router.get("/admin/all")
def get_all_kyc(db: Session = Depends(get_db)):
    kycs = db.query(KYCSubmission).all()
    return {
        "status": "success",
        "count": len(kycs),
        "submissions": [
            {"id": k.id, "userId": k.user_id, "fullName": k.full_name, "idType": k.id_type,
             "status": k.status, "submittedAt": k.submitted_at.isoformat(),
             "reviewedAt": k.reviewed_at.isoformat() if k.reviewed_at else ""}
            for k in kycs
        ],
    }


@router.post("/admin/approve/{kyc_id}")
def approve_kyc(kyc_id: int, admin_name: Optional[str] = None, db: Session = Depends(get_db)):
    kyc = db.query(KYCSubmission).filter(KYCSubmission.id == kyc_id).first()
    if not kyc:
        raise HTTPException(status_code=400, detail="KYC submission not found")

    kyc.status      = "approved"
    kyc.reviewed_at = datetime.utcnow()
    kyc.reviewed_by = admin_name or "admin"

    user = db.query(User).filter(User.id == kyc.user_id).first()
    if user:
        user.kyc_status = "approved"

    db.commit()
    return {"status": "success", "message": "KYC approved successfully", "userId": kyc.user_id}


@router.post("/admin/reject/{kyc_id}")
def reject_kyc(kyc_id: int, body: KYCRejectRequest, db: Session = Depends(get_db)):
    kyc = db.query(KYCSubmission).filter(KYCSubmission.id == kyc_id).first()
    if not kyc:
        raise HTTPException(status_code=400, detail="KYC submission not found")

    kyc.status           = "rejected"
    kyc.rejection_reason = body.reason
    kyc.reviewed_at      = datetime.utcnow()
    kyc.reviewed_by      = body.adminName or "admin"

    user = db.query(User).filter(User.id == kyc.user_id).first()
    if user:
        user.kyc_status = "rejected"

    db.commit()
    return {"status": "success", "message": "KYC rejected", "userId": kyc.user_id}
