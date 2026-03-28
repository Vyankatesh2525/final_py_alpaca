# tradin_service.py
from decimal import Decimal
from sqlalchemy.orm import Session
from models import Wallet, Position, Trade, AlpacaToken
from alpaca_client import get_quote, place_market_order, cancel_all_orders
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


def get_alpaca_token(db: Session, user_id: int) -> str:
    """
    Retrieve the stored Connect access token for this user.
    Raises ValueError if the user hasn't linked their Alpaca account yet.
    """
    record = db.query(AlpacaToken).filter(AlpacaToken.user_id == user_id).first()
    if not record:
        raise ValueError("Alpaca account not connected. Please link your Alpaca account first.")
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
    wallet = get_or_create_wallet(db, user_id)
    positions = db.query(Position).filter(Position.user_id == user_id).all()
    return wallet, positions


# ---------------------------------------------------------------------------
# Trading
# ---------------------------------------------------------------------------

def execute_trade(db: Session, user_id: int, symbol: str, amount: float, side: str):
    """
    1. Look up the user's Alpaca Connect access token
    2. Get live price
    3. Validate wallet balance (buy) or position (sell) — no DB changes yet
    4. Place order via Alpaca using the user's own token
    5. Atomically commit wallet + position + trade record in one transaction
    """
    access_token = get_alpaca_token(db, user_id)

    price = get_quote(symbol)
    if price is None:
        raise ValueError("Failed to get live price")

    amount = Decimal(str(amount))
    qty = amount / price
    symbol = symbol.upper()
    wallet = get_or_create_wallet(db, user_id)

    # --- Validate only, no DB changes yet ---
    if side == "buy":
        if wallet.balance < amount:
            raise ValueError("Insufficient wallet balance")

    elif side == "sell":
        position = db.query(Position).filter(
            Position.user_id == user_id,
            Position.symbol == symbol
        ).first()
        if not position:
            raise ValueError("No position found to sell")
        if position.quantity < qty:
            raise ValueError(
                f"Insufficient shares. You have {position.quantity:.8f}, trying to sell {qty:.8f}"
            )
    else:
        raise ValueError("Invalid side, must be 'buy' or 'sell'")

    # --- Place Alpaca order before touching the DB ---
    alpaca_order = place_market_order(symbol, qty, side, access_token)
    if alpaca_order is None:
        cancel_all_orders(access_token)
        alpaca_order = place_market_order(symbol, qty, side, access_token)
        if alpaca_order is None:
            raise ValueError(
                f"Alpaca order failed for {side} {qty} {symbol}. "
                "Check if fractional trading is enabled or try again later."
            )

    # --- Atomically apply all DB changes ---
    try:
        if side == "buy":
            wallet.balance -= amount
            position = db.query(Position).filter(
                Position.user_id == user_id,
                Position.symbol == symbol
            ).first()
            if not position:
                position = Position(
                    user_id=user_id,
                    symbol=symbol,
                    quantity=qty,
                    avg_price=price,
                )
                db.add(position)
            else:
                total_qty = position.quantity + qty
                position.avg_price = (position.quantity * position.avg_price + qty * price) / total_qty
                position.quantity = total_qty
        else:  # sell
            wallet.balance += amount
            position = db.query(Position).filter(
                Position.user_id == user_id,
                Position.symbol == symbol
            ).first()
            position.quantity -= qty
            if position.quantity <= 0:
                db.delete(position)

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
        db.refresh(wallet)
    except Exception as e:
        db.rollback()
        # The Alpaca order was placed but local DB update failed.
        # Log order_id for manual reconciliation.
        order_id = alpaca_order.get("id", "unknown")
        raise ValueError(
            f"Order {order_id} was placed in Alpaca but failed to record locally: {e}. "
            "Please contact support with this order ID."
        )

    return wallet