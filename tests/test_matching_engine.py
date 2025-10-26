import pytest
import asyncio
from decimal import Decimal

from src.order import Order, OrderSide, OrderType
from src.matching_engine import MatchingEngine


class TestMatchingEngine:
    """Test matching engine functionality"""
    
    @pytest.fixture
    async def engine(self):
        return MatchingEngine("BTC-USDT")
    
    @pytest.mark.asyncio
    async def test_limit_order_matching(self, engine):
        """Test basic limit order matching"""
        # Add buy order
        buy_order = Order(
            symbol="BTC-USDT",
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            quantity=Decimal('1.0'),
            price=Decimal('50000.0')
        )
        
        # Add sell order that matches
        sell_order = Order(
            symbol="BTC-USDT",
            order_type=OrderType.LIMIT,
            side=OrderSide.SELL,
            quantity=Decimal('1.0'),
            price=Decimal('50000.0')
        )
        
        # Process buy order (should rest on book)
        trades = await engine.process_order(buy_order)
        assert len(trades) == 0
        assert buy_order.status.value == "open"
        
        # Process sell order (should match)
        trades = await engine.process_order(sell_order)
        assert len(trades) == 1
        assert trades[0].price == Decimal('50000.0')
        assert trades[0].quantity == Decimal('1.0')
        assert sell_order.status.value == "filled"
        assert buy_order.status.value == "filled"
    
    @pytest.mark.asyncio
    async def test_price_time_priority(self, engine):
        """Test price-time priority"""
        # Add multiple buy orders at same price
        buy_order1 = Order(
            symbol="BTC-USDT",
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            quantity=Decimal('1.0'),
            price=Decimal('50000.0')
        )
        
        buy_order2 = Order(
            symbol="BTC-USDT",
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            quantity=Decimal('1.0'),
            price=Decimal('50000.0')
        )
        
        await engine.process_order(buy_order1)
        await engine.process_order(buy_order2)
        
        # Sell order should match with first buy order
        sell_order = Order(
            symbol="BTC-USDT",
            order_type=OrderType.LIMIT,
            side=OrderSide.SELL,
            quantity=Decimal('1.5'),
            price=Decimal('50000.0')
        )
        
        trades = await engine.process_order(sell_order)
        assert len(trades) == 2
        assert trades[0].maker_order_id == buy_order1.order_id
        assert trades[1].maker_order_id == buy_order2.order_id
    
    @pytest.mark.asyncio
    async def test_ioc_order(self, engine):
        """Test Immediate-Or-Cancel order"""
        # Add sell order
        sell_order = Order(
            symbol="BTC-USDT",
            order_type=OrderType.LIMIT,
            side=OrderSide.SELL,
            quantity=Decimal('1.0'),
            price=Decimal('50000.0')
        )
        await engine.process_order(sell_order)
        
        # IOC buy order for more quantity than available
        ioc_order = Order(
            symbol="BTC-USDT",
            order_type=OrderType.IOC,
            side=OrderSide.BUY,
            quantity=Decimal('2.0'),
            price=Decimal('50000.0')
        )
        
        trades = await engine.process_order(ioc_order)
        assert len(trades) == 1
        assert ioc_order.filled_quantity == Decimal('1.0')
        assert ioc_order.status.value == "cancelled"
    
    @pytest.mark.asyncio
    async def test_fok_order(self, engine):
        """Test Fill-Or-Kill order"""
        # Add sell order
        sell_order = Order(
            symbol="BTC-USDT",
            order_type=OrderType.LIMIT,
            side=OrderSide.SELL,
            quantity=Decimal('1.0'),
            price=Decimal('50000.0')
        )
        await engine.process_order(sell_order)
        
        # FOK buy order for more quantity than available
        fok_order = Order(
            symbol="BTC-USDT",
            order_type=OrderType.FOK,
            side=OrderSide.BUY,
            quantity=Decimal('2.0'),
            price=Decimal('50000.0')
        )
        
        trades = await engine.process_order(fok_order)
        assert len(trades) == 0
        assert fok_order.status.value == "cancelled"


if __name__ == "__main__":
    pytest.main([__file__])