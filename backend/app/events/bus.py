from typing import Dict, List, Callable, Any, Optional
import asyncio
from datetime import datetime
from app.core.logging import logger


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    def subscribe(self, event_type: str, handler: Callable):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.debug("event_bus.subscribed", event_type=event_type, handler=handler.__name__)

    def unsubscribe(self, event_type: str, handler: Callable):
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(handler)

    async def publish(self, event_type: str, payload: Dict[str, Any], source: str = "system"):
        event = {
            "id": f"{event_type}-{datetime.utcnow().timestamp()}",
            "type": event_type,
            "source": source,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._queue.put(event)
        logger.info("event_bus.published", event_type=event_type, source=source)

    async def start(self):
        self._running = True
        logger.info("event_bus.started")
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("event_bus.dispatch_error", error=str(e))

    async def _dispatch(self, event: Dict[str, Any]):
        event_type = event["type"]
        handlers = self._subscribers.get(event_type, []) + self._subscribers.get("*", [])

        if not handlers:
            logger.debug("event_bus.no_handlers", event_type=event_type)
            return

        tasks = [asyncio.create_task(h(event)) for h in handlers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                logger.error("event_bus.handler_error", handler=handler.__name__, error=str(result))

    def stop(self):
        self._running = False


event_bus = EventBus()
