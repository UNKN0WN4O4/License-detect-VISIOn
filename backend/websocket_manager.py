import asyncio
import json
from typing import Set, Dict, Any
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.live_connections: Set[WebSocket] = set()
        self.alert_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect_live(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.live_connections.add(websocket)

    async def disconnect_live(self, websocket: WebSocket):
        async with self._lock:
            self.live_connections.discard(websocket)

    async def connect_alerts(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.alert_connections.add(websocket)

    async def disconnect_alerts(self, websocket: WebSocket):
        async with self._lock:
            self.alert_connections.discard(websocket)

    async def broadcast_live(self, message: Dict[str, Any]):
        """Broadcasts detection or live status update to all connected /ws/live clients."""
        if not self.live_connections:
            return

        payload = json.dumps(message)
        dead_connections = set()

        async with self._lock:
            connections = list(self.live_connections)

        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead_connections.add(ws)

        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    self.live_connections.discard(ws)

    async def broadcast_alert(self, message: Dict[str, Any]):
        """Broadcasts security watchlist alert to all connected /ws/alerts clients."""
        if not self.alert_connections:
            return

        payload = json.dumps(message)
        dead_connections = set()

        async with self._lock:
            connections = list(self.alert_connections)

        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead_connections.add(ws)

        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    self.alert_connections.discard(ws)


ws_manager = WebSocketManager()
