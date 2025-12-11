import asyncio
import json
from typing import Dict, Set
from fastapi import WebSocket
from alpaca_client import get_quote
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[WebSocket, Set[str]] = {}
        self.symbol_subscribers: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[websocket] = set()
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            # Remove from symbol subscriptions
            subscribed_symbols = self.active_connections[websocket].copy()
            for symbol in subscribed_symbols:
                self.unsubscribe_symbol(websocket, symbol)
            
            # Remove connection
            del self.active_connections[websocket]
            logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    def subscribe_symbol(self, websocket: WebSocket, symbol: str):
        symbol = symbol.upper()
        if websocket in self.active_connections:
            self.active_connections[websocket].add(symbol)
            
            if symbol not in self.symbol_subscribers:
                self.symbol_subscribers[symbol] = set()
            self.symbol_subscribers[symbol].add(websocket)
            
            logger.info(f"Subscribed to {symbol}. Subscribers: {len(self.symbol_subscribers[symbol])}")

    def unsubscribe_symbol(self, websocket: WebSocket, symbol: str):
        symbol = symbol.upper()
        if websocket in self.active_connections:
            self.active_connections[websocket].discard(symbol)
            
            if symbol in self.symbol_subscribers:
                self.symbol_subscribers[symbol].discard(websocket)
                if not self.symbol_subscribers[symbol]:
                    del self.symbol_subscribers[symbol]

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.disconnect(websocket)

    async def broadcast_to_symbol_subscribers(self, symbol: str, message: str):
        symbol = symbol.upper()
        if symbol in self.symbol_subscribers:
            disconnected = []
            for websocket in self.symbol_subscribers[symbol].copy():
                try:
                    await websocket.send_text(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to {symbol}: {e}")
                    disconnected.append(websocket)
            
            # Clean up disconnected websockets
            for ws in disconnected:
                self.disconnect(ws)

manager = ConnectionManager()

async def price_updater():
    """Background task to fetch and broadcast price updates"""
    while True:
        try:
            # Get all subscribed symbols
            symbols_to_update = list(manager.symbol_subscribers.keys())
            
            for symbol in symbols_to_update:
                try:
                    price = get_quote(symbol)
                    if price:
                        message = json.dumps({
                            "type": "price_update",
                            "symbol": symbol,
                            "price": price,
                            "timestamp": asyncio.get_event_loop().time()
                        })
                        await manager.broadcast_to_symbol_subscribers(symbol, message)
                except Exception as e:
                    logger.error(f"Error updating price for {symbol}: {e}")
            
            # Wait 5 seconds before next update
            await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"Error in price_updater: {e}")
            await asyncio.sleep(10)

# Start the background task
asyncio.create_task(price_updater())