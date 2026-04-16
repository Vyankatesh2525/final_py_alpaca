# Clau Backend (Python / FastAPI)

Python FastAPI service that is the single backend for the Clau app. Handles user authentication, trading, portfolio management, bank integration, financial goals, subscriptions, KYC, real-time price streaming, and Stripe payments.

The previous Spring Boot backend has been decommissioned. This service now owns everything.

---

## Features

- **Full Auth** — signup, login, token refresh, forgot/reset password with email OTP; 7-day JWT access tokens
- **Alpaca Connect (OAuth)** — per-user Alpaca paper trading account linking via OAuth 2.0; each user gets an isolated $100k paper account; tokens encrypted at rest with Fernet
- **Portfolio** — live positions, available cash, and account details fetched directly from the user's Alpaca account; requires a connected Alpaca account
- **Trading** — buy/sell crypto and stocks by dollar amount through the user's connected Alpaca account
- **Live Prices** — REST endpoints for current quote and daily change; WebSocket endpoint for real-time subscriptions
- **Stripe Financial Connections** — link bank accounts; fetch account balances and transactions
- **Stripe Payments** — create payment intents, confirm deposits, issue payouts to connected Stripe accounts
- **Financial Goals** — CRUD for user goals with sub-tasks
- **Subscriptions** — Stripe-based subscription lifecycle; admin accounts bypass payment gate
- **KYC** — document submission and verification workflow
- **User Data** — profile management, learning points, AI message quota tracking
- **Rate Limiting** — per-IP limiting on all routes via SlowAPI

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI + Uvicorn |
| Database | PostgreSQL + SQLAlchemy ORM |
| Auth | python-jose (JWT) + passlib bcrypt |
| Brokerage | Alpaca REST API + Alpaca Connect OAuth 2.0 |
| Payments | Stripe Python SDK |
| Real-time | WebSockets (FastAPI built-in) |
| Token Security | cryptography (Fernet symmetric encryption) |
| Rate Limiting | SlowAPI |
| Email | SMTP via Gmail (password reset OTPs) |

---

## API Reference

### Health
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | None | Liveness + DB connectivity check |

### Authentication
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/signup` | None | Create account |
| POST | `/auth/login` | None | Login, returns access + refresh tokens |
| POST | `/auth/refresh` | None | Exchange refresh token for new access token |
| POST | `/auth/forgot-password` | None | Send OTP reset email |
| POST | `/auth/reset-password` | None | Reset password with OTP |
| GET | `/auth/user/{username}` | JWT | Get user profile info |

### Alpaca Connect
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/alpaca/callback` | None | OAuth redirect receiver — forwards code to app via deep link |
| POST | `/alpaca/connect` | JWT | Exchange OAuth code for access token and store it |
| GET | `/alpaca/status` | JWT | Check if user has a connected Alpaca account |
| DELETE | `/alpaca/disconnect` | JWT | Remove stored Alpaca token |

### Portfolio & Trading
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/portfolio` | JWT | Live cash balance, equity, account info, and open positions from Alpaca; returns 403 if no account connected |
| POST | `/trades` | JWT | Place a buy or sell order via the user's Alpaca account; returns 403 if not connected |

### Prices
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/prices/{symbol}` | None | Current quote for a stock or crypto symbol |
| GET | `/prices/{symbol}/daily` | None | Current price + daily change and percent |

### Wallet
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/wallet/deposit` | JWT | Credit wallet balance |
| POST | `/wallet/withdraw` | JWT | Debit wallet and issue Stripe payout |

### Stripe Payments
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/stripe/create-payment-intent` | None | Create a Stripe PaymentIntent |
| POST | `/stripe/confirm-payment` | JWT | Confirm payment and credit wallet |

### WebSocket
| Path | Description |
|---|---|
| `ws://host/ws/prices` | Subscribe to real-time price updates |

```json
{ "type": "subscribe",   "symbol": "BTC/USD" }
{ "type": "unsubscribe", "symbol": "BTC/USD" }
```

### Router Modules (`/api/`)
| Prefix | Description |
|---|---|
| `/api/userdata/` | User profile, points, AI message quota |
| `/api/goals/` | Financial goals CRUD with sub-tasks |
| `/api/subscription/` | Subscription status, create, cancel, verify |
| `/api/stripe/` | Stripe Financial Connections — create session, save accounts, fetch accounts/transactions |
| `/api/kyc/` | KYC document submission and status |

---

## Project Structure

```
final_py_alpaca/
├── main.py               # FastAPI app, core route definitions
├── routers/
│   ├── userdata.py       # User profile + points
│   ├── goals.py          # Financial goals
│   ├── subscription.py   # Subscription lifecycle
│   ├── stripe_banking.py # Stripe Financial Connections
│   └── kyc.py            # KYC workflow
├── auth_models.py        # SQLAlchemy User model
├── auth_schemas.py       # Pydantic schemas for auth
├── auth_utils.py         # JWT creation/verification, password hashing, 7-day tokens
├── models.py             # Wallet, Position, Trade, AlpacaToken ORM models
├── schemas.py            # Pydantic schemas for trading/wallet/portfolio
├── database.py           # SQLAlchemy engine and session factory
├── config.py             # Environment variable loading + startup validation
├── alpaca_client.py      # Alpaca market data (quotes, bars) + order placement
├── tradin_service.py     # Portfolio and trade execution logic
├── stripe_service.py     # Stripe payment intent and payout helpers
├── websocket_service.py  # WebSocket connection manager + price updater
├── crypto_utils.py       # Fernet encrypt/decrypt for Alpaca tokens
├── email_service.py      # Gmail SMTP for password reset OTPs
├── create_tables.py      # One-time DB initialisation script
├── update_db.py          # DB migration helper
├── requirements.txt
└── .env
```

---

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL
- Alpaca account (paper trading) with an OAuth app registered at `app.alpaca.markets`
- Stripe account
- Gmail account with App Password enabled (for OTP emails)

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

### 3. Configure `.env`

```env
# PostgreSQL
DATABASE_URL=postgresql+psycopg2://username:password@localhost:5432/clau_db

# Alpaca — static market data keys (paper trading dashboard)
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_SECRET_KEY=your_alpaca_secret_key
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Alpaca Connect — OAuth app credentials (app.alpaca.markets → OAuth Apps)
ALPACA_CLIENT_ID=your_alpaca_oauth_client_id
ALPACA_CLIENT_SECRET=your_alpaca_oauth_client_secret
ALPACA_REDIRECT_URI=https://clau.app/alpaca/callback

# Stripe
STRIPE_SECRET_KEY=your_stripe_secret_key

# JWT signing key
# Generate: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=your_jwt_secret

# Fernet token encryption key (for Alpaca OAuth tokens at rest)
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
TOKEN_ENCRYPTION_KEY=your_fernet_key

# Gmail SMTP (for password reset emails)
MAIL_USERNAME=your_gmail_address
MAIL_PASSWORD=your_gmail_app_password
```

### 4. Create database tables

```bash
python create_tables.py
```

### 5. Run the server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

API available at `http://localhost:8000`
Interactive docs: `http://localhost:8000/docs`

---

## Alpaca Connect Flow

1. Android app opens `AlpacaConnectActivity` which loads the Alpaca OAuth URL in a WebView
2. User authorizes (or creates) their Alpaca paper account
3. Alpaca redirects to `https://clau.app/alpaca/callback?code=...`
4. The `/alpaca/callback` endpoint on this backend redirects to `clauapp://alpaca/callback?code=...` (deep link)
5. The WebView intercepts the deep link before loading it and calls `POST /alpaca/connect` with the code
6. Backend exchanges the code for an access token, encrypts it with Fernet, and stores it per-user
7. All subsequent portfolio and trade requests use that user's personal Alpaca token — users are fully isolated

Users without a connected Alpaca account receive `403` on `/portfolio` and `/trades`.

---

## Deployment

The backend is deployed on AWS EC2. Environment variables are injected via `systemd` service configuration. The app is built with:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Run behind a reverse proxy (nginx) with HTTPS in production.
