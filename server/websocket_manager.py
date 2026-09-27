"""
IBVAP WebSocket Connection Manager
Manages real-time WebSocket client connections, safe client lifecycle,
heartbeats, and resilient broadcast distribution for surveillance events.
"""

import asyncio
import logging
from typing import Any, Dict, List, Set, Union

from fastapi import WebSocket, WebSocketDisconnect

from server.schemas import RealtimeEvent

logger = logging.getLogger("ibvap.websocket")


class WebSocketManager:
    """
    Manages active WebSocket connections for live surveillance event telemetry.
    Thread-safe and async-safe with automatic stale connection pruning.
    """

    def __init__(self):
        self._active_connections: Set[WebSocket] = set()
        self._lock: Optional[asyncio.Lock] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def active_count(self) -> int:
        """Return the number of currently connected WebSocket clients."""
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept an incoming WebSocket connection and register it in active pool."""
        self._loop = asyncio.get_running_loop()
        await websocket.accept()
        async with self._get_lock():
            self._active_connections.add(websocket)
        logger.info(
            f"WebSocket client connected. Total active clients: {len(self._active_connections)}"
        )

        # Send initial connection confirmation
        try:
            await websocket.send_json({
                "message_type": "CONNECTED",
                "service": "IBVAP",
                "active_clients": len(self._active_connections),
            })
        except Exception as e:
            logger.warning(f"Failed to send initial handshake to client: {e}")
            await self.disconnect(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Safely unregister and remove a disconnected WebSocket client."""
        async with self._get_lock():
            if websocket in self._active_connections:
                self._active_connections.remove(websocket)
                logger.info(
                    f"WebSocket client disconnected. Remaining clients: {len(self._active_connections)}"
                )

    async def broadcast_json(self, data: Dict[str, Any]) -> int:
        """
        Broadcast a dictionary payload as JSON to all connected clients.
        Automatically catches and prunes closed or failed connections.

        Returns:
            int: Number of clients that successfully received the message.
        """
        async with self._get_lock():
            clients = list(self._active_connections)

        if not clients:
            return 0

        successful_deliveries = 0
        dead_connections: List[WebSocket] = []

        for client in clients:
            try:
                await client.send_json(data)
                successful_deliveries += 1
            except (WebSocketDisconnect, RuntimeError) as e:
                logger.debug(f"Client disconnected during broadcast: {e}")
                dead_connections.append(client)
            except Exception as e:
                logger.warning(f"Unexpected error broadcasting to client: {e}")
                dead_connections.append(client)

        if dead_connections:
            async with self._get_lock():
                for dead in dead_connections:
                    if dead in self._active_connections:
                        self._active_connections.remove(dead)
            logger.info(
                f"Pruned {len(dead_connections)} stale connections. "
                f"Active clients remaining: {len(self._active_connections)}"
            )

        return successful_deliveries

    async def broadcast_event(self, event: Union[RealtimeEvent, Dict[str, Any]]) -> int:
        """Broadcast a structured RealtimeEvent to all connected clients."""
        payload = (
            event.model_dump()
            if hasattr(event, "model_dump")
            else (event.dict() if hasattr(event, "dict") else dict(event))
        )
        return await self.broadcast_json(payload)

    def broadcast_sync(self, data: Dict[str, Any]) -> None:
        """
        Synchronous bridge to broadcast events from worker threads or sync callbacks.
        Dispatches broadcast_json onto the server's running asyncio event loop.
        """
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.broadcast_json(data))
                return
        except RuntimeError:
            pass

        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast_json(data), self._loop)


# Global singleton instance for application use
ws_manager = WebSocketManager()
