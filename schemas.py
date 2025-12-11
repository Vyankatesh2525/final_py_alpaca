from pydantic import BaseModel, Field
from typing import List, Optional

class DepositRequest(BaseModel):
    amount: float = Field(gt=0, description="Amount to deposit in USD")

class StripeDepositRequest(BaseModel):
    amount: float = Field(gt=0, description="Amount to deposit in USD")

class ConfirmPaymentRequest(BaseModel):
    payment_intent_id: str
    user_id: int

class WithdrawRequest(BaseModel):
    amount: float = Field(gt=0, description="Amount to withdraw in USD")

class TradeRequest(BaseModel):
    user_id: int
    symbol: str
    amount: float = Field(gt=0, description="Dollar amount to invest")
    side: str  # "buy" or "sell"

class WalletResponse(BaseModel):
    balance: float

class PositionResponse(BaseModel):
    symbol: str
    quantity: float
    avg_price: float

class PortfolioResponse(BaseModel):
    balance: float
    positions: List[PositionResponse]