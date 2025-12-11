from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base
from auth_models import User

class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, unique=True)
    balance = Column(Float, default=0.0)
    stripe_account_id = Column(String, nullable=True)
    
    user = relationship("User", back_populates="wallet")


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    symbol = Column(String, index=True)
    quantity = Column(Float, default=0.0)
    avg_price = Column(Float, default=0.0)
    
    user = relationship("User", back_populates="positions")


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    symbol = Column(String, index=True)
    side = Column(String)  # "buy" or "sell"
    qty = Column(Float)
    price = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    order_id = Column(String, nullable=True)  # Alpaca order id
    status = Column(String, default="filled")  # simplified


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    payment_intent_id = Column(String, unique=True, index=True)
    amount = Column(Float)
    status = Column(String)  # "pending", "succeeded", "failed"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())