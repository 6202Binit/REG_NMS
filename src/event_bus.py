import asyncio
from enum import Enum
from typing import Dict, List, Callable, Any
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    TRADE = "trade"
    BBO_UPDATE = "bbo_update"
    ORDER_UPDATE = "order_update"
    SYSTEM = "system"


class EventBus:
    """Event bus for real-time data dissemination"""
    
    def __init__(self):
        self.subscribers: Dict[EventType, List[Callable]] = {
            EventType.TRADE: [],
            EventType.BBO_UPDATE: [],
            EventType.ORDER_UPDATE: [],
            EventType.SYSTEM: []
        }
    
    def subscribe(self, event_type: EventType, callback: Callable):
        """Subscribe to event type"""
        if event_type in self.subscribers:
            self.subscribers[event_type].append(callback)
            logger.debug(f"New subscriber for {event_type.value}")
    
    def unsubscribe(self, event_type: EventType, callback: Callable):
        """Unsubscribe from event type"""
        if event_type in self.subscribers and callback in self.subscribers[event_type]:
            self.subscribers[event_type].remove(callback)
    
    def emit(self, event_type: EventType, data: Any):
        """Emit event to all subscribers"""
        if event_type in self.subscribers:
            for callback in self.subscribers[event_type]:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"Error in event callback: {str(e)}")
    
    async def emit_async(self, event_type: EventType, data: Any):
        """Emit event asynchronously to all subscribers"""
        if event_type in self.subscribers:
            tasks = []
            for callback in self.subscribers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        tasks.append(callback(data))
                    else:
                        # Run sync functions in thread pool
                        loop = asyncio.get_event_loop()
                        tasks.append(loop.run_in_executor(None, callback, data))
                except Exception as e:
                    logger.error(f"Error in async event callback: {str(e)}")
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)