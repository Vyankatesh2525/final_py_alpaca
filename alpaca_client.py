# alpaca_client.py
import logging
import requests
from decimal import Decimal
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL

logger = logging.getLogger(__name__)

# --- Static-key headers (market data only) ---

_STATIC_HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
}

# Crypto symbols traded on Alpaca — these need crypto endpoints and gtc time_in_force
_CRYPTO_SYMBOLS = {
    "BTC", "ETH", "ADA", "ALGO", "SOL", "DOT", "MATIC", "AVAX",
    "LINK", "UNI", "AAVE", "DOGE", "LTC", "XRP", "BCH", "ATOM",
    "XTZ", "SHIB", "BAT", "CRV", "COMP", "MKR", "YFI", "SUSHI",
    "LTCUSD", "BCHUSD", "XRPUSD",  # cover pre-suffixed variants
}


def _is_crypto(symbol: str) -> bool:
    base = symbol.upper().replace("/", "").replace("USD", "")
    return base in _CRYPTO_SYMBOLS or symbol.upper().endswith("USD")


def _trading_headers(access_token: str | None) -> dict:
    """
    Build auth headers for Alpaca trading endpoints.
    If an OAuth Connect token is present, use it (routes the order into the user's own account).
    Falls back to the static API keys (paper trading developer account) when no user token exists —
    useful for testing before Alpaca Connect OAuth approval.
    """
    if access_token:
        return {"Authorization": f"Bearer {access_token}"}
    return _STATIC_HEADERS


# ---------------------------------------------------------------------------
# Market data — always uses static keys, no user token needed
# ---------------------------------------------------------------------------

def get_quote(symbol: str) -> Decimal | None:
    """Get latest trade price for a symbol (stocks or crypto)."""
    symbol = symbol.upper()

    if _is_crypto(symbol):
        # Alpaca crypto data uses BASE/USD format with slash
        base = symbol.replace("USD", "").replace("/", "")
        crypto_sym = f"{base}/USD"
        url = "https://data.alpaca.markets/v1beta3/crypto/us/latest/trades"
        resp = requests.get(url, headers=_STATIC_HEADERS, params={"symbols": crypto_sym}, timeout=10)
        if resp.ok:
            try:
                return Decimal(str(resp.json()["trades"][crypto_sym]["p"]))
            except Exception:
                pass
        logger.warning("Crypto quote failed for %s: %s %s", crypto_sym, resp.status_code, resp.text[:200])
        return None

    # Stock quote
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/trades/latest"
    resp = requests.get(url, headers=_STATIC_HEADERS, timeout=10)
    if not resp.ok:
        logger.warning("Stock quote failed for %s: %s", symbol, resp.status_code)
        return None
    try:
        return Decimal(str(resp.json()["trade"]["p"]))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Trading — requires a per-user Connect access token
# ---------------------------------------------------------------------------

def place_market_order(symbol: str, qty: float, side: str, access_token: str | None) -> dict | None:
    """
    Place a market order on behalf of a connected user.
    Uses their OAuth access token so the order goes into their own Alpaca account.
    Crypto orders use gtc time_in_force and <BASE>/USD symbol format.
    """
    symbol = symbol.upper()
    crypto = _is_crypto(symbol)

    # Alpaca trading API expects BTC/USD format for crypto
    if crypto:
        base = symbol.replace("USD", "").replace("/", "")
        trade_symbol = f"{base}/USD"
        tif = "gtc"
    else:
        trade_symbol = symbol
        tif = "day"

    url = f"{ALPACA_BASE_URL}/v2/orders"
    body = {
        "symbol": trade_symbol,
        "qty": float(qty),
        "side": side,
        "type": "market",
        "time_in_force": tif,
    }

    resp = requests.post(url, json=body, headers=_trading_headers(access_token), timeout=10)

    if not resp.ok:
        error_data = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
        error_code = error_data.get("code")
        logger.warning("Alpaca order rejected for %s %s %s: %s %s", side, qty, trade_symbol, resp.status_code, error_data)

        if error_code == 40310000:
            raise ValueError("Order rejected: wash trade detected. Wait before trading the same stock again.")
        raise ValueError(error_data.get("message", f"Order rejected by Alpaca ({resp.status_code})"))

    return resp.json()


def cancel_all_orders(access_token: str | None) -> bool:
    """Cancel all open orders for a connected user."""
    url = f"{ALPACA_BASE_URL}/v2/orders"
    resp = requests.delete(url, headers=_trading_headers(access_token), timeout=10)
    return resp.ok


def get_alpaca_account(access_token: str | None) -> dict | None:
    """Fetch the Alpaca account details for a connected user (useful for health checks)."""
    url = f"{ALPACA_BASE_URL}/v2/account"
    resp = requests.get(url, headers=_trading_headers(access_token), timeout=10)
    if not resp.ok:
        return None
    return resp.json()


def get_alpaca_positions(access_token: str | None) -> list:
    """Fetch all open positions from the user's Alpaca account."""
    url = f"{ALPACA_BASE_URL}/v2/positions"
    resp = requests.get(url, headers=_trading_headers(access_token), timeout=10)
    if not resp.ok:
        return []
    return resp.json()