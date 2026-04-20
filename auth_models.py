# auth_models.py - SQLAlchemy models for user authentication in Clau Trading Backend.
from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey,
    Index, Integer, String, Text, text,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id                         = Column(Integer, primary_key=True, index=True)
    username                   = Column(String(50), unique=True, nullable=False, index=True)
    full_name                  = Column(String(100))
    email                      = Column(String(100))          # partial unique index: uq_users_email_notnull
    phone_number               = Column(String(20))
    password_hash              = Column(String, nullable=False)
    reset_token                = Column(Text)                 # SHA-256 hash of the 6-digit OTP
    reset_token_expiry         = Column(DateTime)
    token                      = Column(Text)                 # current session JWT
    kyc_status                 = Column(String(20), nullable=False, default="none")
    subscribed                 = Column(Boolean, nullable=False, default=False)
    created_at                 = Column(DateTime, default=datetime.utcnow)
    ai_message_count           = Column(Integer, nullable=False, default=0)
    ai_week_start              = Column(BigInteger)
    learn_points               = Column(Integer, nullable=False, default=0)
    card_points                = Column(Integer, nullable=False, default=0)
    plaid_access_token         = Column(Text)
    is_admin                   = Column(Boolean, nullable=False, default=False)
    stripe_customer_id         = Column(Text)
    stripe_account_ids         = Column(Text)
    stripe_balance_cache       = Column(Text)
    stripe_transactions_cache  = Column(Text)
    stripe_data_synced_at      = Column(DateTime)

    # Relationships
    wallet          = relationship("Wallet",          back_populates="user", uselist=False)
    positions       = relationship("Position",        back_populates="user")
    alpaca_token    = relationship("AlpacaToken",     back_populates="user", uselist=False)
    goals           = relationship("UserGoal",        back_populates="user", cascade="all, delete-orphan")
    kyc_submissions = relationship("KYCSubmission",   back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        # Partial unique index: only enforces uniqueness when email is NOT NULL,
        # allowing multiple rows with email=NULL (users who didn't provide one).
        Index("uq_users_email_notnull", "email", unique=True, postgresql_where=text("email IS NOT NULL")),
    )


class UserGoal(Base):
    __tablename__ = "user_goals"

    id         = Column(String(36), primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title      = Column(String(500), nullable=False)
    created_at = Column(BigInteger, nullable=False)
    sub_tasks  = Column(Text, nullable=False, default="[]")

    user = relationship("User", back_populates="goals")

    __table_args__ = (
        Index("idx_user_goals_user_id", "user_id"),
    )


class KYCSubmission(Base):
    __tablename__ = "kyc_submissions"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name        = Column(String(100), nullable=False)
    date_of_birth    = Column(Date, nullable=False)
    id_type          = Column(String(50), nullable=False)
    id_number        = Column(String(100), nullable=False)
    address          = Column(Text, nullable=False)
    phone            = Column(String(20), nullable=False)
    front_doc_url    = Column(Text)
    back_doc_url     = Column(Text)
    status           = Column(String(20), nullable=False, default="pending", index=True)
    rejection_reason = Column(Text)
    submitted_at     = Column(DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at      = Column(DateTime)
    reviewed_by      = Column(String(100))

    user = relationship("User", back_populates="kyc_submissions")

    __table_args__ = (
        Index("idx_kyc_user_id", "user_id"),
        Index("idx_kyc_status", "status"),
    )
