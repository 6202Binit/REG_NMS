import asyncio
import json
import time
from decimal import Decimal
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
import uvicorn

# Import all necessary classes
from src.order import Order, OrderSide, OrderType
from src.matching_engine import MatchingEngine
from src.persistence import PersistenceManager
from src.event_bus import EventType
from config import Config


# Pydantic models for API
class OrderRequest(BaseModel):
    symbol: str
    order_type: str
    side: str
    quantity: str
    price: Optional[str] = None
    stop_price: Optional[str] = None

class OrderResponse(BaseModel):
    order_id: str
    status: str
    filled_quantity: str
    remaining_quantity: str
    timestamp: float

class CancelRequest(BaseModel):
    order_id: str
    symbol: str


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {
            "market_data": [],
            "trades": []
        }
    
    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        self.active_connections[channel].append(websocket)
    
    def disconnect(self, websocket: WebSocket, channel: str):
        if websocket in self.active_connections[channel]:
            self.active_connections[channel].remove(websocket)
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
    
    async def broadcast(self, message: dict, channel: str):
        disconnected = []
        for websocket in self.active_connections[channel]:
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)
        
        for websocket in disconnected:
            self.disconnect(websocket, channel)


class APIServer:
    def __init__(self):
        self.app = FastAPI(title="Cryptocurrency Matching Engine", version="1.0.0")
        self.matching_engines: Dict[str, MatchingEngine] = {}
        self.connection_manager = ConnectionManager()
        self.persistence = PersistenceManager()
        
        self._setup_routes()
    
    def _setup_routes(self):
        @self.app.post("/orders", response_model=OrderResponse)
        async def submit_order(order_request: OrderRequest):
            try:
                engine = self._get_matching_engine(order_request.symbol)
                
                # Map string order_type to OrderType enum
                order_type_map = {
                    "market": OrderType.MARKET,
                    "limit": OrderType.LIMIT,
                    "ioc": OrderType.IOC,
                    "fok": OrderType.FOK,
                    "stop_loss": OrderType.STOP_LOSS,
                    "stop_limit": OrderType.STOP_LIMIT,
                    "take_profit": OrderType.TAKE_PROFIT
                }
                
                # Map string side to OrderSide enum
                side_map = {
                    "buy": OrderSide.BUY,
                    "sell": OrderSide.SELL
                }
                
                if order_request.order_type not in order_type_map:
                    raise HTTPException(status_code=400, detail=f"Invalid order type: {order_request.order_type}")
                
                if order_request.side not in side_map:
                    raise HTTPException(status_code=400, detail=f"Invalid side: {order_request.side}")
                
                # Create order object
                order = Order(
                    symbol=order_request.symbol,
                    order_type=order_type_map[order_request.order_type],
                    side=side_map[order_request.side],
                    quantity=Decimal(order_request.quantity),
                    price=Decimal(order_request.price) if order_request.price else None,
                    stop_price=Decimal(order_request.stop_price) if order_request.stop_price else None
                )
                
                # Process order
                trades = await engine.process_order(order)
                
                # Broadcast trades
                for trade in trades:
                    await self.connection_manager.broadcast(trade.to_dict(), "trades")
                
                return OrderResponse(
                    order_id=order.order_id,
                    status=order.status.value,
                    filled_quantity=str(order.filled_quantity),
                    remaining_quantity=str(order.remaining_quantity),
                    timestamp=order.timestamp
                )
                
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.delete("/orders")
        async def cancel_order(cancel_request: CancelRequest):
            try:
                engine = self._get_matching_engine(cancel_request.symbol)
                cancelled_order = engine.cancel_order(cancel_request.order_id)
                
                if not cancelled_order:
                    raise HTTPException(status_code=404, detail="Order not found")
                
                return {"status": "cancelled", "order_id": cancel_request.order_id}
                
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.get("/orderbook/{symbol}")
        async def get_orderbook(symbol: str, depth: int = 10):
            try:
                engine = self._get_matching_engine(symbol)
                snapshot = engine.get_order_book_snapshot()
                
                if depth < len(snapshot["bids"]):
                    snapshot["bids"] = snapshot["bids"][:depth]
                if depth < len(snapshot["asks"]):
                    snapshot["asks"] = snapshot["asks"][:depth]
                
                return snapshot
                
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.get("/symbols")
        async def get_symbols():
            return {"symbols": list(self.matching_engines.keys())}
        
        @self.app.websocket("/ws/market-data")
        async def websocket_market_data(websocket: WebSocket):
            await self.connection_manager.connect(websocket, "market_data")
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self.connection_manager.disconnect(websocket, "market_data")
        
        @self.app.websocket("/ws/trades")
        async def websocket_trades(websocket: WebSocket):
            await self.connection_manager.connect(websocket, "trades")
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self.connection_manager.disconnect(websocket, "trades")
        
        @self.app.on_event("startup")
        async def startup_event():
            await self._initialize_engines()
        
        @self.app.on_event("shutdown")
        async def shutdown_event():
            await self._save_state()
    
    def _get_matching_engine(self, symbol: str) -> MatchingEngine:
        if symbol not in self.matching_engines:
            self.matching_engines[symbol] = MatchingEngine(symbol)
            
            engine = self.matching_engines[symbol]
            engine.event_bus.subscribe(
                EventType.BBO_UPDATE,
                lambda data: asyncio.create_task(
                    self.connection_manager.broadcast(data, "market_data")
                )
            )
        
        return self.matching_engines[symbol]
    
    async def _initialize_engines(self):
        try:
            state = await self.persistence.load_state()
            
            for symbol, symbol_state in state.get("order_books", {}).items():
                order_book = self.persistence.restore_order_book(state, symbol)
                engine = MatchingEngine(symbol)
                engine.order_book = order_book
                self.matching_engines[symbol] = engine
                
                engine.event_bus.subscribe(
                    EventType.BBO_UPDATE,
                    lambda data: asyncio.create_task(
                        self.connection_manager.broadcast(data, "market_data")
                    )
                )
                
                print(f"Restored matching engine for {symbol}")
                
        except Exception as e:
            print(f"Error initializing engines: {str(e)}")
    
    async def _save_state(self):
        try:
            await self.persistence.save_state(
                {symbol: engine.order_book for symbol, engine in self.matching_engines.items()}
            )
        except Exception as e:
            print(f"Error saving state: {str(e)}")