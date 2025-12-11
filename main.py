from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
import json
import asyncio
from database import Base, engine, get_db
from schemas import (
    DepositRequest,
    WithdrawRequest,
    TradeRequest,
    WalletResponse,
    PortfolioResponse,
    PositionResponse,
    StripeDepositRequest,
    ConfirmPaymentRequest,
)
from auth_schemas import LoginRequest, SignupRequest, LoginResponse, SignupResponse
from auth_models import User
from auth_utils import hash_password, verify_password, create_access_token, get_current_user_id
from tradin_service import deposit, withdraw, get_portfolio, execute_trade
from stripe_service import create_payment_intent, confirm_payment, create_connected_account, attach_test_bank_account, create_payout_to_user, fund_test_account
from websocket_service import manager, price_updater

app = FastAPI(title="Clau Trading Backend")

# Create tables
Base.metadata.create_all(bind=engine)

# Start price updater background task
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(price_updater())


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/wallet/deposit", response_model=WalletResponse)
def deposit_money(body: DepositRequest, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """
    Fake deposit for testing (no Stripe).
    """
    wallet = deposit(db, user_id, body.amount)
    return WalletResponse(balance=wallet.balance)


@app.post("/stripe/create-payment-intent")
def create_stripe_payment_intent(body: StripeDepositRequest):
    """
    Create a Stripe payment intent for deposit.
    """
    result = create_payment_intent(body.amount)
    return result


@app.post("/stripe/confirm-payment", response_model=WalletResponse)
def confirm_stripe_payment(body: ConfirmPaymentRequest, db: Session = Depends(get_db)):
    """
    Confirm Stripe payment and add money to wallet.
    """
    payment_result = confirm_payment(body.payment_intent_id)
    
    if payment_result.get("status") == "succeeded":
        amount = payment_result.get("amount", 0)
        wallet = deposit(db, body.user_id, amount)
        return WalletResponse(balance=wallet.balance)
    else:
        raise HTTPException(status_code=400, detail="Payment not successful")


@app.post("/wallet/withdraw", response_model=WalletResponse)
def withdraw_money(body: WithdrawRequest, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from models import Wallet
    
    # Get wallet
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
    if not wallet or wallet.balance < body.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    
    try:
        # Use existing Stripe connected account
        if not wallet.stripe_account_id:
            # Use your existing connected account
            wallet.stripe_account_id = "acct_1Sd31uCfyiF2HfaC"
            print(f"Using existing Stripe account: {wallet.stripe_account_id}")
            db.commit()
        
        # Create payout
        print(f"Creating payout of ${body.amount} for account {wallet.stripe_account_id}")
        payout_result = create_payout_to_user(wallet.stripe_account_id, body.amount)
        
        if payout_result.get("status") in ["paid", "pending"]:
            # Decrease wallet balance
            wallet.balance -= body.amount
            db.commit()
            print(f"Payout successful! New balance: {wallet.balance}")
            return WalletResponse(balance=wallet.balance)
        else:
            print(f"Payout failed: {payout_result.get('error')}")
            raise HTTPException(status_code=400, detail=f"Payout failed: {payout_result.get('error')}")
            
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Unexpected error: {str(e)}")
        print(f"Full traceback: {error_details}")
        raise HTTPException(status_code=500, detail=f"Withdrawal failed: {str(e)}")


@app.get("/portfolio", response_model=PortfolioResponse)
def get_user_portfolio(user_id: int = None, db: Session = Depends(get_db)):
    # Accept user_id as query parameter for testing
    if user_id is None:
        raise HTTPException(status_code=400, detail="user_id is required")
    
    wallet, positions = get_portfolio(db, user_id)
    return PortfolioResponse(
        balance=wallet.balance,
        positions=[
            PositionResponse(
                symbol=p.symbol,
                quantity=p.quantity,
                avg_price=p.avg_price
            )
            for p in positions
        ]
    )


@app.post("/trades", response_model=WalletResponse)
def place_trade(body: TradeRequest, db: Session = Depends(get_db)):
    """
    Buy or sell using dollar amount + Alpaca.
    """
    try:
        wallet = execute_trade(
            db,
            user_id=body.user_id,
            symbol=body.symbol,
            amount=body.amount,
            side=body.side.lower(),
        )
        return WalletResponse(balance=wallet.balance)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.websocket("/ws/prices")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "subscribe":
                symbol = message["symbol"]
                manager.subscribe_symbol(websocket, symbol)
                await manager.send_personal_message(
                    json.dumps({
                        "type": "subscribed",
                        "symbol": symbol.upper(),
                        "message": f"Subscribed to {symbol.upper()} price updates"
                    }),
                    websocket
                )
            
            elif message["type"] == "unsubscribe":
                symbol = message["symbol"]
                manager.unsubscribe_symbol(websocket, symbol)
                await manager.send_personal_message(
                    json.dumps({
                        "type": "unsubscribed",
                        "symbol": symbol.upper(),
                        "message": f"Unsubscribed from {symbol.upper()} price updates"
                    }),
                    websocket
                )
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/prices/{symbol}")
def get_current_price(symbol: str):
    """Get current price for a symbol (REST endpoint)"""
    from alpaca_client import get_quote
    price = get_quote(symbol)
    if price:
        return {"symbol": symbol.upper(), "price": price}
    else:
        raise HTTPException(status_code=404, detail="Price not found")

@app.get("/prices/{symbol}/daily")
def get_daily_price_data(symbol: str):
    """Get current and previous close prices for daily change calculation"""
    from alpaca_client import get_quote
    current_price = get_quote(symbol)
    if current_price:
        # Simulate previous close (in production, use real historical data)
        import random
        previous_close = current_price * (0.95 + random.random() * 0.1)
        daily_change = current_price - previous_close
        daily_change_percent = (daily_change / previous_close) * 100
        
        return {
            "symbol": symbol.upper(),
            "current_price": current_price,
            "previous_close": previous_close,
            "daily_change": daily_change,
            "daily_change_percent": daily_change_percent
        }
    else:
        raise HTTPException(status_code=404, detail="Price not found")


# Authentication endpoints
@app.post("/auth/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"user_id": user.id})
    return LoginResponse(
        access_token=token,
        user_id=user.id,
        message="Login successful"
    )

@app.post("/auth/signup", response_model=SignupResponse)
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == request.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    
    user = User(
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create wallet for new user only if it doesn't exist
    from models import Wallet
    existing_wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    if not existing_wallet:
        wallet = Wallet(user_id=user.id, balance=0.0)
        db.add(wallet)
        db.commit()
    
    return SignupResponse(message="User created successfully")

@app.get("/")
def root():
    return {"message": "Clau Trading API", "status": "running", "features": ["trading", "payments", "real-time-prices", "authentication"]}