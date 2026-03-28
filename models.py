# models.py
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base
from auth_models import User

class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, unique=True)
    balance = Column(Numeric(18, 2), default=0)
    stripe_account_id = Column(String, nullable=True)
    
    user = relationship("User", back_populates="wallet")


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    symbol = Column(String, index=True)
    quantity = Column(Numeric(18, 8), default=0)
    avg_price = Column(Numeric(18, 8), default=0)
    
    user = relationship("User", back_populates="positions")


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    symbol = Column(String, index=True)
    side = Column(String)  # "buy" or "sell"
    qty = Column(Numeric(18, 8))
    price = Column(Numeric(18, 8))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    order_id = Column(String, nullable=True)
    status = Column(String, default="filled")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    payment_intent_id = Column(String, unique=True, index=True)
    amount = Column(Numeric(18, 2))
    status = Column(String)  # "pending", "succeeded", "failed"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AlpacaToken(Base):
    __tablename__ = "alpaca_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)
    access_token = Column(String, nullable=False)
    # Alpaca Connect tokens don't expire by default, but store refresh_token
    # and expires_at for future-proofing if Alpaca adds rotation.
    refresh_token = Column(String, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="alpaca_token")