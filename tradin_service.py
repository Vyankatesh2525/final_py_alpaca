from sqlalchemy.orm import Session
from models import Wallet, Position, Trade
from alpaca_client import get_quote, place_market_order

def get_or_create_wallet(db: Session, user_id: int) -> Wallet:
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0.0)
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
    return wallet


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


def get_portfolio(db: Session, user_id: int):
    wallet = get_or_create_wallet(db, user_id)
    positions = db.query(Position).filter(Position.user_id == user_id).all()
    return wallet, positions


def execute_trade(db: Session, user_id: int, symbol: str, qty: float, side: str):
    """
    1. Get price from Alpaca
    2. Check wallet balance (for buy)
    3. Place order (Alpaca)
    4. Update wallet + positions
    5. Save Trade
    """
    price = get_quote(symbol)
    if price is None:
        raise ValueError("Failed to get live price")

    wallet = get_or_create_wallet(db, user_id)
    cost = price * qty

    if side == "buy":
        if wallet.balance < cost:
            raise ValueError("Insufficient wallet balance")
        wallet.balance -= cost
    elif side == "sell":
        # Check position
        position = db.query(Position).filter(
            Position.user_id == user_id,
            Position.symbol == symbol.upper()
        ).first()
        if not position or position.quantity < qty:
            raise ValueError("Insufficient position to sell")
        # Add to wallet
        wallet.balance += cost
    else:
        raise ValueError("Invalid side, must be 'buy' or 'sell'")

    # Place order in Alpaca
    alpaca_order = place_market_order(symbol, qty, side)
    if alpaca_order is None:
        raise ValueError("Alpaca order failed")

    # Update positions
    position = db.query(Position).filter(
        Position.user_id == user_id,
        Position.symbol == symbol.upper()
    ).first()

    if side == "buy":
        if not position:
            position = Position(
                user_id=user_id,
                symbol=symbol.upper(),
                quantity=qty,
                avg_price=price
            )
            db.add(position)
        else:
            # New avg price = (old_qty*old_price + new_qty*price) / (old_qty + new_qty)
            total_qty = position.quantity + qty
            position.avg_price = (position.quantity * position.avg_price + qty * price) / total_qty
            position.quantity = total_qty
    else:  # sell
        if position:
            position.quantity -= qty
            if position.quantity <= 0:
                db.delete(position)

    # Save trade
    trade = Trade(
        user_id=user_id,
        symbol=symbol.upper(),
        side=side,
        qty=qty,
        price=price,
        order_id=alpaca_order.get("id"),
        status=alpaca_order.get("status", "filled")
    )
    db.add(trade)

    db.commit()
    db.refresh(wallet)
    return wallet