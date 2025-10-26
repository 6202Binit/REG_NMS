import json
import asyncio
from typing import Dict, Any, List
from decimal import Decimal
import logging

from src.order import Order, OrderType, OrderSide, OrderStatus
from src.order_book import OrderBook

logger = logging.getLogger(__name__)


class PersistenceManager:
    """Manages order book state persistence and recovery"""
    
    def __init__(self, state_file: str = "order_book_state.json"):
        self.state_file = state_file
    
    async def save_state(self, order_books: Dict[str, OrderBook]):
        """Save complete order book state to JSON file"""
        try:
            state = {
                "timestamp": asyncio.get_event_loop().time(),
                "order_books": {}
            }
            
            for symbol, order_book in order_books.items():
                symbol_state = {
                    "symbol": symbol,
                    "orders": [],
                    "bbo": {
                        "best_bid": str(order_book.get_best_bid()) if order_book.get_best_bid() else None,
                        "best_ask": str(order_book.get_best_ask()) if order_book.get_best_ask() else None
                    }
                }
                
                # Save all open orders
                for order in order_book.orders.values():
                    if order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
                        symbol_state["orders"].append(order.to_dict())
                
                state["order_books"][symbol] = symbol_state
            
            # Save to file asynchronously
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            logger.info(f"Order book state saved to {self.state_file}")
            
        except Exception as e:
            logger.error(f"Error saving state: {str(e)}")
            raise
    
    async def load_state(self) -> Dict[str, Any]:
        """Load order book state from JSON file"""
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            logger.info(f"Order book state loaded from {self.state_file}")
            return state
            
        except FileNotFoundError:
            logger.warning(f"State file {self.state_file} not found, starting fresh")
            return {}
        except Exception as e:
            logger.error(f"Error loading state: {str(e)}")
            raise
    
    def restore_order_book(self, state: Dict[str, Any], symbol: str) -> OrderBook:
        """Restore order book from saved state"""
        if symbol not in state.get("order_books", {}):
            return OrderBook(symbol)
        
        symbol_state = state["order_books"][symbol]
        order_book = OrderBook(symbol)
        
        # Restore orders
        for order_data in symbol_state["orders"]:
            try:
                order = Order.from_dict(order_data)
                order_book.add_order(order)
            except Exception as e:
                logger.error(f"Error restoring order {order_data.get('order_id')}: {str(e)}")
        
        logger.info(f"Restored {len(symbol_state['orders'])} orders for {symbol}")
        return order_book