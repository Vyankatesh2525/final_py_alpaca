# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# "development" (default) or "production"
# Set APP_ENV=production in your systemd EnvironmentFile on EC2.
APP_ENV = os.getenv("APP_ENV", "development")
IS_PRODUCTION = APP_ENV == "production"

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://user:password@localhost:5432/clau_db")

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
STRIPE_SECRET_KEY      = os.getenv("STRIPE_SECRET_KEY", "")
# Webhook signing secret from the Stripe dashboard → Developers → Webhooks.
# Run: stripe listen --forward-to localhost:8000/api/stripe/webhook  (dev)
STRIPE_WEBHOOK_SECRET  = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Gmail SMTP — used for password reset OTP emails
# Reads MAIL_USERNAME / MAIL_PASSWORD to match the existing .env convention.
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("MAIL_USERNAME", "")
SMTP_PASSWORD = os.getenv("MAIL_PASSWORD", "")

# JWT
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY environment variable is not set")

# Token encryption (Fernet) — generate with:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
TOKEN_ENCRYPTION_KEY = os.getenv("TOKEN_ENCRYPTION_KEY")
if not TOKEN_ENCRYPTION_KEY:
    raise RuntimeError("TOKEN_ENCRYPTION_KEY environment variable is not set")

# Production-only hard requirements — crash fast on EC2 if anything is missing.
# In development, missing third-party keys are tolerated (those features just won't work).
if IS_PRODUCTION:
    if DATABASE_URL == "postgresql+psycopg2://user:password@localhost:5432/clau_db":
        raise RuntimeError("DATABASE_URL must be set to a real value in production")
    if not ALPACA_API_KEY:
        raise RuntimeError("ALPACA_API_KEY environment variable is not set")
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("STRIPE_SECRET_KEY environment variable is not set")