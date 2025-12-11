from sqlalchemy.orm import Session
from models import Payment
from database import SessionLocal

def log_payment_attempt(user_id: int, payment_intent_id: str, status: str):
    db = SessionLocal()
    try:
        payment = Payment(
            user_id=user_id,
            payment_intent_id=payment_intent_id,
            status=status,
            amount=0.0  # You can update this with actual amount
        )
        db.add(payment)
        db.commit()
        print(f"Logged payment: {payment_intent_id} - {status}")
    except Exception as e:
        print(f"Error logging payment: {e}")
        db.rollback()
    finally:
        db.close()