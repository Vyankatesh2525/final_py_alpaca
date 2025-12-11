from database import engine, Base
from models import Wallet, Position, Trade, Payment
from auth_models import User

# Create all tables
Base.metadata.create_all(bind=engine)
print("All tables created successfully!")