import requests
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
}

def get_quote(symbol: str) -> float | None:
    """
    Get latest trade price (LTP) for symbol.
    """
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/trades/latest"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if not resp.ok:
        print("Alpaca quote error:", resp.status_code, resp.text)
        return None

    data = resp.json()
    try:
        return float(data["trade"]["p"])  # price
    except Exception as e:
        print("Error parsing quote:", e, data)
        return None


def place_market_order(symbol: str, qty: float, side: str) -> dict | None:
    """
    Place a market order via Alpaca.
    side: "buy" or "sell"
    """
    url = f"{ALPACA_BASE_URL}/v2/orders"
    body = {
        "symbol": symbol.upper(),
        "qty": qty,
        "side": side,
        "type": "market",
        "time_in_force": "day",
    }
    resp = requests.post(url, json=body, headers=HEADERS, timeout=10)
    if not resp.ok:
        print("Alpaca order error:", resp.status_code, resp.text)
        return None

    return resp.json()