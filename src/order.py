import uuid
import time
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    IOC = "ioc"
    FOK = "fok"
    STOP_LOSS = "stop_loss"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT = "take_profit"

class OrderStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

@dataclass
class Order:
    symbol: str
    order_type: OrderType
    side: OrderSide
    quantity: Decimal
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    order_id: str = None
    timestamp: float = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = Decimal('0')
    remaining_quantity: Decimal = None
    
    def __post_init__(self):
        if self.order_id is None:
            self.order_id = str(uuid.uuid4())[:16]
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.remaining_quantity is None:
            self.remaining_quantity = self.quantity
            
        self._validate()
    
    def _validate(self):
        if self.quantity <= Decimal('0'):
            raise ValueError("Quantity must be positive")
        
        if self.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and self.price is None:
            raise ValueError("Limit orders require a price")
        
        if self.order_type in [OrderType.STOP_LOSS, OrderType.STOP_LIMIT, OrderType.TAKE_PROFIT] and self.stop_price is None:
            raise ValueError("Stop orders require a stop price")
    
    def update_fill(self, fill_quantity: Decimal):
        self.filled_quantity += fill_quantity
        self.remaining_quantity -= fill_quantity
        
        if self.remaining_quantity <= Decimal('0'):
            self.status = OrderStatus.FILLED
        elif self.filled_quantity > Decimal('0'):
            self.status = OrderStatus.PARTIALLY_FILLED
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['order_type'] = self.order_type.value
        data['side'] = self.side.value
        data['status'] = self.status.value
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = str(value)
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Order':
        for key in ['quantity', 'price', 'stop_price', 'filled_quantity', 'remaining_quantity']:
            if key in data and data[key] is not None:
                data[key] = Decimal(str(data[key]))
        
        data['order_type'] = OrderType(data['order_type'])
        data['side'] = OrderSide(data['side'])
        data['status'] = OrderStatus(data['status'])
        
        return cls(**data)