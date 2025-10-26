import decimal
from decimal import Decimal

# Decimal precision settings
decimal.getcontext().prec = 10
decimal.getcontext().rounding = decimal.ROUND_HALF_UP

class Config:
    # Fee structure
    MAKER_FEE_RATE = Decimal('0.001')  # 0.1%
    TAKER_FEE_RATE = Decimal('0.002')  # 0.2%
    
    # Performance settings
    MAX_ORDER_BOOK_DEPTH = 1000
    ORDER_ID_LENGTH = 16
    TRADE_ID_LENGTH = 20
    
    # API settings
    HOST = "0.0.0.0"
    PORT = 8000
    DEBUG = False
    
    # Persistence
    STATE_FILE = "order_book_state.json"
    
    # Logging
    LOG_LEVEL = "INFO"