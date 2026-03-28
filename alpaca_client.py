# alpaca_client.py
import requests
from decimal import Decimal
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL

# --- Static-key headers (market data only) ---

_STATIC_HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
}


def _trading_headers(access_token: str) -> dict:
    """Build Authorization header for a per-user Connect token."""
    return {"Authorization": f"Bearer {access_token}"}


# ---------------------------------------------------------------------------
# Market data — always uses static keys, no user token needed
# ---------------------------------------------------------------------------

def get_quote(symbol: str) -> Decimal | None:
    """Get latest trade price for a symbol."""
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/trades/latest"
    resp = requests.get(url, headers=_STATIC_HEADERS, timeout=10)
    if not resp.ok:
        return None
    try:
        return Decimal(str(resp.json()["trade"]["p"]))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Trading — requires a per-user Connect access token
# ---------------------------------------------------------------------------

def place_market_order(symbol: str, qty: float, side: str, access_token: str) -> dict | None:
    """
    Place a market order on behalf of a connected user.
    Uses their OAuth access token so the order goes into their own Alpaca account.
    """
    url = f"{ALPACA_BASE_URL}/v2/orders"
    body = {
        "symbol": symbol.upper(),
        "qty": qty,
        "side": side,
        "type": "market",
        "time_in_force": "day",
    }

    resp = requests.post(url, json=body, headers=_trading_headers(access_token), timeout=10)

    if not resp.ok:
        error_data = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
        error_code = error_data.get("code")

        if error_code == 40310000:
            raise ValueError("Order rejected: wash trade detected. Wait before trading the same stock again.")
        return None

    return resp.json()


def cancel_all_orders(access_token: str) -> bool:
    """Cancel all open orders for a connected user."""
    url = f"{ALPACA_BASE_URL}/v2/orders"
    resp = requests.delete(url, headers=_trading_headers(access_token), timeout=10)
    return resp.ok


def get_alpaca_account(access_token: str) -> dict | None:
    """Fetch the Alpaca account details for a connected user (useful for health checks)."""
    url = f"{ALPACA_BASE_URL}/v2/account"
    resp = requests.get(url, headers=_trading_headers(access_token), timeout=10)
    if not resp.ok:
        return None
    return resp.json()