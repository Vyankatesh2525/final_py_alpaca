# main.py
import logging
import json
import asyncio
import requests

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import RedirectResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import Base, engine, get_db
from routers import userdata, goals, subscription, stripe_banking, kyc
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
from auth_schemas import (
    LoginRequest, SignupRequest, LoginResponse, SignupResponse,
    RefreshTokenRequest, RefreshTokenResponse,
    ForgotPasswordRequest, ResetPasswordRequest, UserInfoResponse,
)
from auth_models import User
from auth_utils import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    get_current_user_id, get_user_id_from_refresh_token,
    generate_reset_token, hash_token,
)
from email_service import send_password_reset_email
from tradin_service import deposit, withdraw, get_portfolio, execute_trade
from stripe_service import create_payment_intent, confirm_payment, create_payout_to_user
from websocket_service import manager, price_updater
from models import AlpacaToken
from crypto_utils import encrypt_token
from config import ALPACA_CLIENT_ID, ALPACA_CLIENT_SECRET, ALPACA_REDIRECT_URI, ALPACA_TOKEN_URL, ALPACA_API_KEY

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Clau Trading Backend", docs_url=None, redoc_url=None)  # disable docs in prod
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

Base.metadata.create_all(bind=engine)

app.include_router(userdata.router)
app.include_router(goals.router)
app.include_router(subscription.router)
app.include_router(stripe_banking.router)
app.include_router(kyc.router)

_price_updater_task = None


@app.on_event("startup")
async def startup_event():
    global _price_updater_task
    _price_updater_task = asyncio.create_task(price_updater())


@app.on_event("shutdown")
async def shutdown_event():
    if _price_updater_task:
        _price_updater_task.cancel()
        try:
            await _price_updater_task
        except asyncio.CancelledError:
            pass
    logger.info("Server shutdown complete")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    status = "ok" if db_status == "ok" else "degraded"
    return {"status": status, "db": db_status}


# ---------------------------------------------------------------------------
# Alpaca OAuth web callback — receives redirect from Alpaca, forwards to app
# ---------------------------------------------------------------------------

@app.get("/alpaca/callback")
def alpaca_oauth_callback(code: str = None, error: str = None):
    """
    Alpaca redirects the user's browser here after authorization.
    We forward the code to the Android app via its custom URI scheme.
    Register https://clau.app/alpaca/callback in the Alpaca dashboard.
    """
    if error:
        return RedirectResponse(url=f"clauapp://alpaca/callback?error={error}")
    if not code:
        return RedirectResponse(url="clauapp://alpaca/callback?error=missing_code")
    return RedirectResponse(url=f"clauapp://alpaca/callback?code={code}")


# ---------------------------------------------------------------------------
# Alpaca Connect (OAuth)
# ---------------------------------------------------------------------------

class AlpacaConnectRequest(BaseModel):
    code: str


class AlpacaConnectStatus(BaseModel):
    connected: bool


@app.post("/alpaca/connect")
@limiter.limit("10/minute")
def alpaca_connect(
    request: Request,
    body: AlpacaConnectRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    resp = requests.post(
        ALPACA_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": body.code,
            "client_id": ALPACA_CLIENT_ID,
            "client_secret": ALPACA_CLIENT_SECRET,
            "redirect_uri": ALPACA_REDIRECT_URI,
        },
        timeout=15,
    )

    if not resp.ok:
        logger.error("Alpaca token exchange failed: status=%s", resp.status_code)
        raise HTTPException(status_code=400, detail="Failed to exchange Alpaca authorization code")

    token_data = resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token in Alpaca response")

    record = db.query(AlpacaToken).filter(AlpacaToken.user_id == user_id).first()
    encrypted = encrypt_token(access_token)
    if record:
        record.access_token = encrypted
        record.refresh_token = token_data.get("refresh_token")
    else:
        record = AlpacaToken(
            user_id=user_id,
            access_token=encrypted,
            refresh_token=token_data.get("refresh_token"),
        )
        db.add(record)

    db.commit()
    return {"message": "Alpaca account connected successfully"}


@app.get("/alpaca/status", response_model=AlpacaConnectStatus)
def alpaca_status(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    record = db.query(AlpacaToken).filter(AlpacaToken.user_id == user_id).first()
    # Consider connected if the user has an OAuth token OR if static API keys are
    # configured (paper trading fallback while Alpaca Connect approval is pending).
    connected = record is not None or bool(ALPACA_API_KEY)
    return AlpacaConnectStatus(connected=connected)


@app.delete("/alpaca/disconnect")
def alpaca_disconnect(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    record = db.query(AlpacaToken).filter(AlpacaToken.user_id == user_id).first()
    if record:
        db.delete(record)
        db.commit()
    return {"message": "Alpaca account disconnected"}


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------

@app.post("/wallet/deposit", response_model=WalletResponse)
@limiter.limit("10/minute")
def deposit_money(request: Request, body: DepositRequest, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    wallet = deposit(db, user_id, body.amount)
    return WalletResponse(balance=wallet.balance)


@app.post("/stripe/create-payment-intent")
@limiter.limit("10/minute")
def create_stripe_payment_intent(request: Request, body: StripeDepositRequest):
    result = create_payment_intent(body.amount)
    return result


@app.post("/stripe/confirm-payment", response_model=WalletResponse)
@limiter.limit("10/minute")
def confirm_stripe_payment(
    request: Request,
    body: ConfirmPaymentRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    payment_result = confirm_payment(body.payment_intent_id, body.payment_method_id)
    if payment_result.get("status") == "succeeded":
        amount = payment_result.get("amount", 0)
        wallet = deposit(db, user_id, amount)
        return WalletResponse(balance=wallet.balance)
    raise HTTPException(status_code=400, detail="Payment not successful")


@app.post("/wallet/withdraw", response_model=WalletResponse)
@limiter.limit("5/minute")
def withdraw_money(request: Request, body: WithdrawRequest, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from models import Wallet

    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
    if not wallet or wallet.balance < body.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    if not wallet.stripe_account_id:
        raise HTTPException(
            status_code=400,
            detail="No payout account linked. Please connect a bank account before withdrawing."
        )

    try:
        payout_result = create_payout_to_user(wallet.stripe_account_id, body.amount)

        if payout_result.get("status") in ["paid", "pending"]:
            wallet.balance -= body.amount
            db.commit()
            return WalletResponse(balance=wallet.balance)

        raise HTTPException(status_code=400, detail="Payout could not be completed")

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error during withdrawal for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail="Withdrawal failed. Please try again later.")


# ---------------------------------------------------------------------------
# Portfolio & Trading
# ---------------------------------------------------------------------------

@app.get("/portfolio", response_model=PortfolioResponse)
def get_user_portfolio(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    wallet, positions = get_portfolio(db, user_id)
    return PortfolioResponse(
        balance=wallet.balance,
        positions=[
            PositionResponse(symbol=p.symbol, quantity=p.quantity, avg_price=p.avg_price)
            for p in positions
        ],
    )


@app.post("/trades", response_model=WalletResponse)
@limiter.limit("20/minute")
def place_trade(request: Request, body: TradeRequest, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    try:
        wallet = execute_trade(
            db,
            user_id=user_id,
            symbol=body.symbol,
            amount=body.amount,
            side=body.side,
        )
        return WalletResponse(balance=wallet.balance)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Unexpected error during trade for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail="Trade could not be executed. Please try again.")


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------

@app.get("/prices/{symbol}")
@limiter.limit("60/minute")
def get_current_price(request: Request, symbol: str):
    from alpaca_client import get_quote
    price = get_quote(symbol)
    if price:
        return {"symbol": symbol.upper(), "price": price}
    raise HTTPException(status_code=404, detail="Price not found")


@app.get("/prices/{symbol}/daily")
@limiter.limit("60/minute")
def get_daily_price_data(request: Request, symbol: str):
    from alpaca_client import get_quote
    import random
    current_price = get_quote(symbol)
    if current_price:
        previous_close = current_price * (0.95 + random.random() * 0.1)
        daily_change = current_price - previous_close
        daily_change_percent = (daily_change / previous_close) * 100
        return {
            "symbol": symbol.upper(),
            "current_price": current_price,
            "previous_close": previous_close,
            "daily_change": daily_change,
            "daily_change_percent": daily_change_percent,
        }
    raise HTTPException(status_code=404, detail="Price not found")


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

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
                    json.dumps({"type": "subscribed", "symbol": symbol.upper()}),
                    websocket,
                )
            elif message["type"] == "unsubscribe":
                symbol = message["symbol"]
                manager.unsubscribe_symbol(websocket, symbol)
                await manager.send_personal_message(
                    json.dumps({"type": "unsubscribed", "symbol": symbol.upper()}),
                    websocket,
                )
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/auth/login", response_model=LoginResponse)
@limiter.limit("5/minute")
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    # Accept username or email
    user = (
        db.query(User).filter(User.username == body.username).first()
        or db.query(User).filter(User.email == body.username).first()
    )
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token  = create_access_token({"user_id": user.id})
    refresh_token = create_refresh_token({"user_id": user.id})

    # Persist the current JWT so token-based endpoints (userdata, stripe) can look it up.
    user.token = access_token
    db.commit()

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id,
        is_admin=bool(user.is_admin),
        message="Login successful",
    )


@app.post("/auth/signup", response_model=SignupResponse)
@limiter.limit("3/minute")
def signup(request: Request, body: SignupRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if body.email and db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    user = User(
        username=body.username,
        full_name=body.full_name,
        email=body.email,
        phone_number=body.phone_number,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Generate JWT now that we have a real user ID, and store it.
    jwt_token = create_access_token({"user_id": user.id})
    user.token = jwt_token
    db.commit()

    from models import Wallet
    if not db.query(Wallet).filter(Wallet.user_id == user.id).first():
        db.add(Wallet(user_id=user.id, balance=0.0))
        db.commit()

    return SignupResponse(message="User registered successfully", status="success", token=jwt_token)


@app.post("/auth/refresh", response_model=RefreshTokenResponse)
@limiter.limit("10/minute")
def refresh_token(request: Request, body: RefreshTokenRequest, db: Session = Depends(get_db)):
    user_id = get_user_id_from_refresh_token(body.refresh_token)
    new_access_token = create_access_token({"user_id": user_id})

    # Keep stored token in sync so authenticate-by-token endpoints stay valid.
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.token = new_access_token
        db.commit()

    return RefreshTokenResponse(access_token=new_access_token, message="Token refreshed")


@app.get("/auth/user/{username}", response_model=UserInfoResponse)
def get_user_info(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserInfoResponse(
        username=user.username,
        full_name=user.full_name or "",
        email=user.email or "",
        phone_number=user.phone_number or "",
    )


@app.post("/auth/forgot-password")
@limiter.limit("3/minute")
def forgot_password(request: Request, body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Accept username or email in the `username` field.
    user = (
        db.query(User).filter(User.username == body.username).first()
        or db.query(User).filter(User.email == body.username).first()
    )
    if not user:
        raise HTTPException(status_code=400, detail="No account found with this username or email")
    if not user.email:
        raise HTTPException(status_code=400, detail="No email address on file for this account")

    from datetime import datetime, timedelta
    otp, token_hash = generate_reset_token()
    user.reset_token        = token_hash
    user.reset_token_expiry = datetime.utcnow() + timedelta(minutes=15)
    db.commit()

    sent = send_password_reset_email(user.email, otp)
    if not sent:
        logger.error("Failed to send reset email for user_id=%s", user.id)
        raise HTTPException(status_code=500, detail="Could not send reset email — please try again later")

    return {"message": "Password reset code sent to your email", "status": "success"}


@app.post("/auth/reset-password")
@limiter.limit("5/minute")
def reset_password(request: Request, body: ResetPasswordRequest, db: Session = Depends(get_db)):
    from datetime import datetime
    token_hash = hash_token(body.token)
    user = db.query(User).filter(User.reset_token == token_hash).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset code")

    if not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Reset code has expired")

    user.password_hash      = hash_password(body.new_password)
    user.reset_token        = None
    user.reset_token_expiry = None
    db.commit()

    return {"message": "Password reset successfully", "status": "success"}


@app.get("/")
def root():
    return {"message": "Clau Trading API", "status": "running"}
