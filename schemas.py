# schemas.py - Pydantic schemas for request and response models in Clau Trading Backend.
from pydantic import BaseModel, Field
from typing import List, Literal
import re

class DepositRequest(BaseModel):
    amount: float = Field(gt=0, le=100000, description="Amount to deposit in USD")

class StripeDepositRequest(BaseModel):
    amount: float = Field(gt=0, le=100000, description="Amount to deposit in USD")

class ConfirmPaymentRequest(BaseModel):
    payment_intent_id: str = Field(min_length=1, max_length=100)
    payment_method_id: str = Field(min_length=1, max_length=100)

class WithdrawRequest(BaseModel):
    amount: float = Field(gt=0, le=100000, description="Amount to withdraw in USD")

class TradeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=10, pattern=r"^[A-Z0-9/]+$")
    amount: float = Field(gt=0, le=1000000, description="Dollar amount to invest")
    side: Literal["buy", "sell"]

class WalletResponse(BaseModel):
    balance: float

class PositionResponse(BaseModel):
    symbol: str
    quantity: float
    avg_price: float

class PortfolioResponse(BaseModel):
    balance: float
    positions: List[PositionResponse]
