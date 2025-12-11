from sqlalchemy.orm import Session
from models import Wallet, Position, Trade
from alpaca_client import get_quote, place_market_order, cancel_all_orders

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


def execute_trade(db: Session, user_id: int, symbol: str, amount: float, side: str):
    """
    1. Get price from Alpaca
    2. Calculate quantity from dollar amount
    3. Check wallet balance (for buy)
    4. Place order (Alpaca)
    5. Update wallet + positions
    6. Save Trade
    """
    price = get_quote(symbol)
    if price is None:
        raise ValueError("Failed to get live price")

    # Calculate quantity from dollar amount
    qty = amount / price
    wallet = get_or_create_wallet(db, user_id)
    cost = amount  # Use the exact dollar amount

    if side == "buy":
        if wallet.balance < amount:
            raise ValueError("Insufficient wallet balance")
        wallet.balance -= amount
    elif side == "sell":
        # For sell orders, amount represents dollar value to sell
        # Calculate how many shares to sell based on dollar amount
        position = db.query(Position).filter(
            Position.user_id == user_id,
            Position.symbol == symbol.upper()
        ).first()
        if not position:
            raise ValueError("No position found to sell")
        
        # Calculate shares to sell based on dollar amount
        qty = amount / price
        if position.quantity < qty:
            raise ValueError(f"Insufficient shares. You have {position.quantity}, trying to sell {qty}")
        
        # Add exact dollar amount to wallet
        wallet.balance += amount
    else:
        raise ValueError("Invalid side, must be 'buy' or 'sell'")

    # Place order in Alpaca
    alpaca_order = place_market_order(symbol, qty, side)
    if alpaca_order is None:
        # Try cancelling existing orders and retry once
        print(f"Order failed, trying to cancel existing orders and retry...")
        cancel_all_orders()
        alpaca_order = place_market_order(symbol, qty, side)
        
        if alpaca_order is None:
            raise ValueError(f"Alpaca order failed for {side} {qty} {symbol}. Check if fractional trading is enabled or wait before trading the same stock.")

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
        order_id=alpaca_order.get("id", f"order_{symbol}_{int(qty*1000)}"),
        status=alpaca_order.get("status", "filled")
    )
    db.add(trade)

    db.commit()
    db.refresh(wallet)
    return wallet