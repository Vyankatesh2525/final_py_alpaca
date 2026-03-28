# Clau Trading Backend (Python / FastAPI)

Python FastAPI service that handles trading, wallet management, real-time price streaming, and Stripe payments. Connects to the Android app and the Spring Boot auth backend.

---

## Features

- **JWT Authentication** — stateless auth using signed tokens; every protected route requires a Bearer token issued by the auth backend
- **Alpaca Connect (OAuth)** — per-user Alpaca brokerage account linking via OAuth 2.0; tokens are encrypted at rest with Fernet
- **Wallet** — internal balance ledger per user; deposit and withdraw via Stripe
- **Trading** — buy/sell crypto and stocks by dollar amount using the user's connected Alpaca account
- **Portfolio** — fetch live positions and wallet balance
- **Live Prices** — REST endpoints for current quote and daily change; WebSocket endpoint for real-time price subscriptions
- **Stripe Integration** — create payment intents, confirm deposits, and issue payouts to connected accounts
- **Rate Limiting** — per-IP rate limiting on all routes via SlowAPI

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| Database | PostgreSQL + SQLAlchemy ORM |
| Auth | python-jose (JWT) + passlib bcrypt |
| Brokerage | alpaca-py (market data) + Alpaca OAuth (trading) |
| Payments | Stripe |
| Real-time | WebSockets (built-in FastAPI) |
| Token Security | cryptography (Fernet symmetric encryption) |
| Rate Limiting | SlowAPI |

---

## API Reference

### Health
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | None | Liveness check |

### Alpaca Connect
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/alpaca/connect` | JWT | Exchange OAuth code for access token and store it |
| GET | `/alpaca/status` | JWT | Check if user has a connected Alpaca account |
| DELETE | `/alpaca/disconnect` | JWT | Remove stored Alpaca token |

### Wallet
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/wallet/deposit` | JWT | Credit wallet balance directly |
| POST | `/wallet/withdraw` | JWT | Debit wallet and issue Stripe payout |

### Stripe
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/stripe/create-payment-intent` | None | Create a Stripe PaymentIntent |
| POST | `/stripe/confirm-payment` | None | Confirm payment and credit wallet on success |

### Portfolio & Trading
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/portfolio` | None* | Wallet balance + open positions |
| POST | `/trades` | None* | Place a buy or sell order via Alpaca |

### Prices
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/prices/{symbol}` | None | Current quote for a symbol |
| GET | `/prices/{symbol}/daily` | None | Current price + daily change/percent |

### WebSocket
| Path | Description |
|---|---|
| `ws://host/ws/prices` | Subscribe/unsubscribe to real-time price updates |

**Subscribe message:**
```json
{ "type": "subscribe", "symbol": "BTC/USD" }
```
**Unsubscribe message:**
```json
{ "type": "unsubscribe", "symbol": "BTC/USD" }
```

---

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL database
- Alpaca account (paper or live) + OAuth app registered
- Stripe account

### 1. Clone and create virtual environment

```bash
git clone <repo-url>
cd final_py_alpaca
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# PostgreSQL
DATABASE_URL=postgresql+psycopg2://username:password@localhost:5432/database_name

# Alpaca — static market data keys
ALPACA_API_KEY=your_alpaca_api_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Alpaca Connect — OAuth app credentials
ALPACA_CLIENT_ID=your_alpaca_oauth_client_id
ALPACA_CLIENT_SECRET=your_alpaca_oauth_client_secret
ALPACA_REDIRECT_URI=clauapp://alpaca/callback

# Stripe
STRIPE_SECRET_KEY=your_stripe_secret_key_here
STRIPE_PUBLISHABLE_KEY=your_stripe_publishable_key_here

# JWT signing key — generate with:
# python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=your_jwt_secret_here

# Fernet token encryption key — generate with:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
TOKEN_ENCRYPTION_KEY=your_fernet_key_here
```

### 4. Create database tables

```bash
python create_tables.py
```

### 5. Run the server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

---

## Project Structure

```
final_py_alpaca/
├── main.py               # FastAPI app, all route definitions
├── auth_models.py        # SQLAlchemy User model
├── auth_schemas.py       # Pydantic schemas for auth requests/responses
├── auth_utils.py         # JWT creation/verification, password hashing
├── models.py             # Wallet, Position, AlpacaToken ORM models
├── schemas.py            # Pydantic schemas for trading/wallet
├── database.py           # SQLAlchemy engine and session factory
├── config.py             # Environment variable loading
├── alpaca_client.py      # Alpaca market data (quotes, bars, assets)
├── tradin_service.py     # Deposit, withdraw, portfolio, trade logic
├── stripe_service.py     # Stripe payment intent and payout helpers
├── websocket_service.py  # WebSocket connection manager + price updater
├── crypto_utils.py       # Fernet encrypt/decrypt for Alpaca tokens
├── create_tables.py      # One-time DB initialisation script
├── update_db.py          # DB migration helper
├── requirements.txt
└── .env.example
```
