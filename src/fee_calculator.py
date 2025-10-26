from decimal import Decimal
from typing import Tuple
from config import Config


class FeeCalculator:
    """Implements maker-taker fee model"""
    
    def __init__(self, maker_fee_rate: Decimal = None, taker_fee_rate: Decimal = None):
        self.maker_fee_rate = maker_fee_rate or Config.MAKER_FEE_RATE
        self.taker_fee_rate = taker_fee_rate or Config.TAKER_FEE_RATE
    
    def calculate_maker_fee(self, price: Decimal, quantity: Decimal) -> Decimal:
        """Calculate maker fee: Fee = Notional Value × Fee Rate"""
        notional_value = price * quantity
        return notional_value * self.maker_fee_rate
    
    def calculate_taker_fee(self, price: Decimal, quantity: Decimal) -> Decimal:
        """Calculate taker fee: Fee = Notional Value × Fee Rate"""
        notional_value = price * quantity
        return notional_value * self.taker_fee_rate
    
    def calculate_total_fees(self, price: Decimal, quantity: Decimal) -> Tuple[Decimal, Decimal]:
        """Calculate both maker and taker fees"""
        maker_fee = self.calculate_maker_fee(price, quantity)
        taker_fee = self.calculate_taker_fee(price, quantity)
        return maker_fee, taker_fee