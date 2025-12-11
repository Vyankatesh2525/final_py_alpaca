from sqlalchemy import text
from database import engine

# Add the missing column
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE wallets ADD COLUMN stripe_account_id VARCHAR"))
        conn.commit()
        print("✅ Added stripe_account_id column successfully!")
    except Exception as e:
        if "already exists" in str(e):
            print("✅ Column already exists!")
        else:
            print(f"❌ Error: {e}")