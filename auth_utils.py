# auth_utils.py - Authentication utilities for Clau Trading Backend, including password hashing and JWT handling.
import hashlib
import secrets
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from config import JWT_SECRET_KEY

# Password hashing - using pbkdf2_sha256 as fallback if bcrypt issues persist
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    deprecated="auto",
    pbkdf2_sha256__rounds=30000
)

ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60  # 1 hour access token
REFRESH_TOKEN_EXPIRE_DAYS = 30  # 30-day refresh token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password[:72], hashed)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)

def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_user_id_from_refresh_token(token: str) -> int:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")


# ---------------------------------------------------------------------------
# Password reset helpers
# ---------------------------------------------------------------------------

def generate_reset_token() -> tuple[str, str]:
    """
    Returns (raw_otp, sha256_hash).
    raw_otp   — 6-digit string sent to the user by email.
    sha256_hash — what is stored in the database (never store raw OTP).
    """
    otp = f"{secrets.randbelow(1_000_000):06d}"
    return otp, hash_token(otp)


def hash_token(token: str) -> str:
    """SHA-256 hex digest of the given string (used for reset token storage)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()