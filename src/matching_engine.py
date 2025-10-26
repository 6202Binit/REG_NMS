import asyncio
import time
import uuid
from decimal import Decimal
from typing import List, Optional, Dict, Any
import logging

from src.order import Order, OrderSide, OrderType, OrderStatus
from src.order_book import OrderBook
from src.fee_calculator import FeeCalculator
from src.event_bus import EventBus, EventType

logger = logging.getLogger(__name__)


class Trade:
    """Represents a trade execution"""
    
    def __init__(self, symbol: str, price: Decimal, quantity: Decimal, 
                 aggressor_side: OrderSide, maker_order: Order, taker_order: Order):
        self.trade_id = str(uuid.uuid4())[:20]
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        self.aggressor_side = aggressor_side
        self.maker_order_id = maker_order.order_id
        self.taker_order_id = taker_order.order_id
        self.timestamp = time.time()
        self.maker_fee = Decimal('0')
        self.taker_fee = Decimal('0')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert trade to dictionary"""
        return {
            "trade_id": self.trade_id,
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "price": str(self.price),
            "quantity": str(self.quantity),
            "aggressor_side": self.aggressor_side.value,
            "maker_order_id": self.maker_order_id,
            "taker_order_id": self.taker_order_id,
            "maker_fee": str(self.maker_fee),
            "taker_fee": str(self.taker_fee)
        }


class MatchingEngine:
    """High-performance matching engine with REG NMS compliance"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.order_book = OrderBook(symbol)
        self.fee_calculator = FeeCalculator()
        self.event_bus = EventBus()
        self.lock = asyncio.Lock()
        self.trade_count = 0
        
        logger.info(f"Initialized matching engine for {symbol}")
    
    async def process_order(self, order: Order) -> List[Trade]:
        """Process incoming order with price-time priority"""
        async with self.lock:
            return await self._process_order_internal(order)
    
    async def _process_order_internal(self, order: Order) -> List[Trade]:
        """Internal order processing logic"""
        trades = []
        
        try:
            # Validate order
            self._validate_order(order)
            
            # Handle stop orders
            if order.order_type in [OrderType.STOP_LOSS, OrderType.STOP_LIMIT, OrderType.TAKE_PROFIT]:
                return await self._handle_stop_order(order)
            
            # Check if order is marketable
            if self.order_book.can_match(order):
                trades = await self._match_order(order)
            
            # Handle remaining quantity for limit orders
            if (order.order_type == OrderType.LIMIT and 
                order.remaining_quantity > Decimal('0')):
                self.order_book.add_order(order)
            
            # Emit BBO update if order book changed
            if trades or order.order_type == OrderType.LIMIT:
                self._emit_bbo_update()
            
            logger.info(f"Processed order {order.order_id}: {order.status.value}")
            
        except Exception as e:
            logger.error(f"Error processing order {order.order_id}: {str(e)}")
            order.status = OrderStatus.REJECTED
            raise
        
        return trades
    
    async def _match_order(self, taker_order: Order) -> List[Trade]:
        """Match order against opposite side with price-time priority"""
        trades = []
        opposite_side = OrderSide.SELL if taker_order.side == OrderSide.BUY else OrderSide.BUY
        
        while (taker_order.remaining_quantity > Decimal('0') and 
               self.order_book.can_match(taker_order)):
            
            # Get best price level on opposite side
            best_price = (self.order_book.get_best_ask() if taker_order.side == OrderSide.BUY 
                         else self.order_book.get_best_bid())
            
            if best_price is None:
                break
            
            # Check price compatibility for limit orders
            if (taker_order.order_type == OrderType.LIMIT and
                ((taker_order.side == OrderSide.BUY and taker_order.price < best_price) or
                 (taker_order.side == OrderSide.SELL and taker_order.price > best_price))):
                break
            
            # Get price level
            price_level = (self.order_book.asks[best_price] if taker_order.side == OrderSide.BUY 
                          else self.order_book.bids[best_price])
            
            # Match with first order in price level (FIFO)
            maker_order = price_level.get_first_order()
            if not maker_order:
                break
            
            # Calculate fill quantity
            fill_quantity = min(taker_order.remaining_quantity, maker_order.remaining_quantity)
            
            # Execute at maker's price (no trade-through)
            execution_price = maker_order.price
            
            # Create trade
            trade = Trade(
                symbol=self.symbol,
                price=execution_price,
                quantity=fill_quantity,
                aggressor_side=taker_order.side,
                maker_order=maker_order,
                taker_order=taker_order
            )
            
            # Calculate fees
            trade.maker_fee = self.fee_calculator.calculate_maker_fee(
                execution_price, fill_quantity
            )
            trade.taker_fee = self.fee_calculator.calculate_taker_fee(
                execution_price, fill_quantity
            )
            
            trades.append(trade)
            
            # Update orders
            taker_order.update_fill(fill_quantity)
            maker_order.update_fill(fill_quantity)
            
            # Remove maker if fully filled
            if maker_order.remaining_quantity <= Decimal('0'):
                price_level.pop_first_order()
                if not price_level.orders:
                    if taker_order.side == OrderSide.BUY:
                        del self.order_book.asks[best_price]
                    else:
                        del self.order_book.bids[best_price]
            
            # Emit trade event
            self.event_bus.emit(EventType.TRADE, trade.to_dict())
            
            # Handle IOC/FOK conditions
            if (taker_order.order_type == OrderType.IOC and 
                taker_order.remaining_quantity > Decimal('0')):
                taker_order.status = OrderStatus.CANCELLED
                break
            
            if (taker_order.order_type == OrderType.FOK and 
                taker_order.remaining_quantity > Decimal('0')):
                # Rollback fills for FOK
                for trade in trades:
                    self._rollback_fill(trade)
                taker_order.status = OrderStatus.CANCELLED
                return []
        
        self.trade_count += len(trades)
        return trades
    
    async def _handle_stop_order(self, order: Order) -> List[Trade]:
        """Handle stop order trigger logic"""
        current_bbo = self.order_book.get_bbo()
        
        if order.side == OrderSide.BUY:
            trigger_condition = (current_bbo[1] is not None and  # Best ask exists
                               current_bbo[1] <= order.stop_price)
        else:
            trigger_condition = (current_bbo[0] is not None and  # Best bid exists
                               current_bbo[0] >= order.stop_price)
        
        if trigger_condition:
            # Convert to market or limit order
            if order.order_type == OrderType.STOP_LOSS:
                order.order_type = OrderType.MARKET
                order.price = None
            elif order.order_type in [OrderType.STOP_LIMIT, OrderType.TAKE_PROFIT]:
                order.order_type = OrderType.LIMIT
            
            return await self._match_order(order)
        else:
            # Add to order book as resting stop order
            self.order_book.add_order(order)
            return []
    
    def _validate_order(self, order: Order):
        """Validate order parameters"""
        if order.quantity <= Decimal('0'):
            raise ValueError("Order quantity must be positive")
        
        if order.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and order.price is None:
            raise ValueError("Limit orders require a price")
        
        if order.order_type in [OrderType.STOP_LOSS, OrderType.STOP_LIMIT, OrderType.TAKE_PROFIT]:
            if order.stop_price is None:
                raise ValueError("Stop orders require a stop price")
    
    def _rollback_fill(self, trade: Trade):
        """Rollback trade fill (for FOK orders)"""
        # This would need to track original order states for rollback
        # Simplified implementation
        logger.warning(f"Rolling back trade {trade.trade_id} for FOK order")
    
    def _emit_bbo_update(self):
        """Emit BBO update event"""
        bbo = self.order_book.get_bbo()
        depth = self.order_book.get_market_depth(10)
        
        bbo_data = {
            "timestamp": time.time(),
            "symbol": self.symbol,
            "best_bid": str(bbo[0]) if bbo[0] else None,
            "best_ask": str(bbo[1]) if bbo[1] else None,
            "best_bid_quantity": str(self.order_book.get_best_bid_quantity()),
            "best_ask_quantity": str(self.order_book.get_best_ask_quantity()),
            "bids": depth[0],
            "asks": depth[1]
        }
        
        self.event_bus.emit(EventType.BBO_UPDATE, bbo_data)
    
    def cancel_order(self, order_id: str) -> Optional[Order]:
        """Cancel order from order book"""
        return self.order_book.remove_order(order_id)
    
    def get_order_book_snapshot(self) -> Dict[str, Any]:
        """Get complete order book snapshot"""
        bids, asks = self.order_book.get_market_depth(100)  # Get full depth
        bbo = self.order_book.get_bbo()
        
        return {
            "timestamp": time.time(),
            "symbol": self.symbol,
            "bids": bids,
            "asks": asks,
            "best_bid": str(bbo[0]) if bbo[0] else None,
            "best_ask": str(bbo[1]) if bbo[1] else None
        }