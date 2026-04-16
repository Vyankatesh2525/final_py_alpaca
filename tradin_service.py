# tradin_service.py
from decimal import Decimal
from sqlalchemy.orm import Session
from models import Wallet, Position, Trade, AlpacaToken
from alpaca_client import get_quote, place_market_order, cancel_all_orders, get_alpaca_account, get_alpaca_positions
from crypto_utils import decrypt_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_or_create_wallet(db: Session, user_id: int) -> Wallet:
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0.0)
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
    return wallet


def get_alpaca_token(db: Session, user_id: int) -> str | None:
    """
    Retrieve the stored Connect access token for this user.
    Returns None if the user hasn't linked their Alpaca account — alpaca_client
    will then fall back to the static developer API keys (paper trading account).
    """
    record = db.query(AlpacaToken).filter(AlpacaToken.user_id == user_id).first()
    if not record:
        return None
    return decrypt_token(record.access_token)


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------

def deposit(db: Session, user_id: int, amount: float) -> Wallet:
    wallet = get_or_create_wallet(db, user_id)
    wallet.balance += amount
    db.commit()
    db.refresh(wallet)
    return wallet


def withdraw(db: Session, user_id: int, amount: float) -> Wallet | None:
    wallet = get_or_create_wallet(db, user_id)
    if wallet.balance < amount:
        return None
    wallet.balance -= amount
    db.commit()
    db.refresh(wallet)
    return wallet


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

def get_portfolio(db: Session, user_id: int):
    """Return (alpaca_account_dict, alpaca_positions_list) from the live Alpaca account."""
    access_token = get_alpaca_token(db, user_id)
    if not access_token:
        raise PermissionError("Alpaca account not connected")
    account = get_alpaca_account(access_token)
    positions = get_alpaca_positions(access_token)
    return account, positions


# ---------------------------------------------------------------------------
# Trading
# ---------------------------------------------------------------------------

def execute_trade(db: Session, user_id: int, symbol: str, amount: float, side: str) -> float:
    """
    1. Look up the user's Alpaca Connect access token
    2. Get live price
    3. Place order via Alpaca — Alpaca validates balance/position on their end
    4. Record the trade locally for history
    5. Return updated buying_power from the Alpaca account
    """
    access_token = get_alpaca_token(db, user_id)
    if not access_token:
        raise PermissionError("Alpaca account not connected")

    price = get_quote(symbol)
    if price is None:
        raise ValueError("Failed to get live price")

    amount = Decimal(str(amount))
    qty = amount / price
    symbol = symbol.upper()

    if side not in ("buy", "sell"):
        raise ValueError("Invalid side, must be 'buy' or 'sell'")

    # --- Place Alpaca order — Alpaca handles balance and position validation ---
    alpaca_order = place_market_order(symbol, qty, side, access_token)
    if alpaca_order is None:
        cancel_all_orders(access_token)
        alpaca_order = place_market_order(symbol, qty, side, access_token)
        if alpaca_order is None:
            raise ValueError(
                f"Alpaca order failed for {side} {qty} {symbol}. "
                "Check if fractional trading is enabled or try again later."
            )

    # --- Record trade locally for history ---
    try:
        trade = Trade(
            user_id=user_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            order_id=alpaca_order.get("id"),
            status=alpaca_order.get("status", "filled"),
        )
        db.add(trade)
        db.commit()
    except Exception as e:
        db.rollback()
        order_id = alpaca_order.get("id", "unknown")
        raise ValueError(
            f"Order {order_id} was placed in Alpaca but failed to record locally: {e}. "
            "Please contact support with this order ID."
        )

    # Return live buying_power from Alpaca
    account = get_alpaca_account(access_token)
    return float(account.get("cash", 0.0)) if account else 0.0