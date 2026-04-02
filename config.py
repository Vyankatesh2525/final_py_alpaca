# config.py
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://user:password@localhost:5432/clau_trading_db")

# Alpaca static keys — used only for market data (quotes, bars)
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# Alpaca Connect OAuth — used for per-user trading via Connect
ALPACA_CLIENT_ID = os.getenv("ALPACA_CLIENT_ID", "")
ALPACA_CLIENT_SECRET = os.getenv("ALPACA_CLIENT_SECRET", "")
# The redirect URI must exactly match what you register in the Alpaca dashboard
ALPACA_REDIRECT_URI = os.getenv("ALPACA_REDIRECT_URI", "https://clau.app/alpaca/callback")
# Token exchange endpoint
ALPACA_TOKEN_URL = "https://api.alpaca.markets/oauth/token"

# Stripe keys
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")

# JWT
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY environment variable is not set")

# Token encryption (Fernet) — generate with:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
TOKEN_ENCRYPTION_KEY = os.getenv("TOKEN_ENCRYPTION_KEY")
if not TOKEN_ENCRYPTION_KEY:
    raise RuntimeError("TOKEN_ENCRYPTION_KEY environment variable is not set")

# Validate required service credentials on startup
if DATABASE_URL == "postgresql+psycopg2://user:password@localhost:5432/clau_trading_db":
    raise RuntimeError("DATABASE_URL must be set — default placeholder is not a valid production value")

if not ALPACA_API_KEY:
    raise RuntimeError("ALPACA_API_KEY environment variable is not set")

if not STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY environment variable is not set")