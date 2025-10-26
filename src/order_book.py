import heapq
from collections import deque, defaultdict
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from sortedcontainers import SortedDict

from src.order import Order, OrderSide, OrderStatus


class PriceLevel:
    """Represents a price level in the order book with FIFO queue"""
    
    def __init__(self, price: Decimal):
        self.price = price
        self.orders = deque()  # FIFO queue for price-time priority
        self.total_quantity = Decimal('0')
    
    def add_order(self, order: Order):
        """Add order to price level"""
        self.orders.append(order)
        self.total_quantity += order.remaining_quantity
    
    def remove_order(self, order: Order) -> bool:
        """Remove specific order from price level"""
        try:
            self.orders.remove(order)
            self.total_quantity -= order.remaining_quantity
            return True
        except ValueError:
            return False
    
    def get_first_order(self) -> Optional[Order]:
        """Get first order in FIFO queue"""
        return self.orders[0] if self.orders else None
    
    def pop_first_order(self) -> Optional[Order]:
        """Remove and return first order in FIFO queue"""
        if not self.orders:
            return None
        order = self.orders.popleft()
        self.total_quantity -= order.remaining_quantity
        return order
    
    def update_order_quantity(self, old_quantity: Decimal, new_quantity: Decimal):
        """Update total quantity when order quantity changes"""
        self.total_quantity += (new_quantity - old_quantity)


class OrderBook:
    """High-performance order book with price-time priority"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        # SortedDict for efficient price level management
        self.bids = SortedDict(lambda x: -x)  # Descending for bids
        self.asks = SortedDict()  # Ascending for asks
        self.orders = {}  # O(1) order lookup by ID
        self._best_bid: Optional[Decimal] = None
        self._best_ask: Optional[Decimal] = None
    
    def add_order(self, order: Order) -> bool:
        """Add order to order book"""
        if order.order_id in self.orders:
            return False
        
        self.orders[order.order_id] = order
        
        if order.side == OrderSide.BUY:
            price_level = self.bids.setdefault(order.price, PriceLevel(order.price))
            price_level.add_order(order)
        else:  # OrderSide.SELL
            price_level = self.asks.setdefault(order.price, PriceLevel(order.price))
            price_level.add_order(order)
        
        self._update_bbo()
        order.status = OrderStatus.OPEN
        return True
    
    def remove_order(self, order_id: str) -> Optional[Order]:
        """Remove order from order book"""
        order = self.orders.get(order_id)
        if not order:
            return None
        
        del self.orders[order_id]
        
        if order.side == OrderSide.BUY:
            price_level = self.bids.get(order.price)
            if price_level and price_level.remove_order(order):
                if not price_level.orders:
                    del self.bids[order.price]
        else:
            price_level = self.asks.get(order.price)
            if price_level and price_level.remove_order(order):
                if not price_level.orders:
                    del self.asks[order.price]
        
        self._update_bbo()
        order.status = OrderStatus.CANCELLED
        return order
    
    def get_best_bid(self) -> Optional[Decimal]:
        """Get best bid price (O(1))"""
        return self.bids.peekitem(0)[0] if self.bids else None
    
    def get_best_ask(self) -> Optional[Decimal]:
        """Get best ask price (O(1))"""
        return self.asks.peekitem(0)[0] if self.asks else None
    
    def get_bbo(self) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """Get Best Bid and Offer"""
        return self.get_best_bid(), self.get_best_ask()
    
    def get_best_bid_quantity(self) -> Decimal:
        """Get total quantity at best bid"""
        if not self.bids:
            return Decimal('0')
        best_bid_price = self.get_best_bid()
        return self.bids[best_bid_price].total_quantity
    
    def get_best_ask_quantity(self) -> Decimal:
        """Get total quantity at best ask"""
        if not self.asks:
            return Decimal('0')
        best_ask_price = self.get_best_ask()
        return self.asks[best_ask_price].total_quantity
    
    def get_market_depth(self, depth: int = 10) -> Tuple[List[Tuple], List[Tuple]]:
        """Get order book depth (top N levels)"""
        bids_list = []
        asks_list = []
        
        # Get top N bid levels
        for i, (price, level) in enumerate(self.bids.items()):
            if i >= depth:
                break
            bids_list.append((str(price), str(level.total_quantity)))
        
        # Get top N ask levels
        for i, (price, level) in enumerate(self.asks.items()):
            if i >= depth:
                break
            asks_list.append((str(price), str(level.total_quantity)))
        
        return bids_list, asks_list
    
    def _update_bbo(self):
        """Update Best Bid and Offer"""
        self._best_bid = self.get_best_bid()
        self._best_ask = self.get_best_ask()
    
    def can_match(self, order: Order) -> bool:
        """Check if order can be matched against opposite side"""
        if order.side == OrderSide.BUY:
            best_ask = self.get_best_ask()
            return best_ask is not None and (order.order_type == OrderType.MARKET or 
                   order.price >= best_ask)
        else:  # OrderSide.SELL
            best_bid = self.get_best_bid()
            return best_bid is not None and (order.order_type == OrderType.MARKET or 
                   order.price <= best_bid)