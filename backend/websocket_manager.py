"""WebSocket connection manager — session-scoped broadcast hub."""

from __future__ import annotations

import contextlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import WebSocket

IST = ZoneInfo("Asia/Kolkata")


class ConnectionManager:
    def __init__(self) -> None:
        # session_id -> list of WebSocket connections
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        if session_id not in self.active:
            self.active[session_id] = []
        self.active[session_id].append(ws)
        print(
            f"[WS] Client connected to session {session_id} "
            f"({len(self.active[session_id])} clients)"
        )

    def disconnect(self, session_id: str, ws: WebSocket) -> None:
        if session_id in self.active:
            with contextlib.suppress(ValueError):
                self.active[session_id].remove(ws)
            if not self.active[session_id]:
                del self.active[session_id]
        print(f"[WS] Client disconnected from {session_id}")

    async def broadcast(self, session_id: str, event: dict[str, object]) -> None:
        if session_id not in self.active:
            return
        event["ist_timestamp"] = datetime.now(IST).isoformat()
        message = json.dumps(event, ensure_ascii=False)
        dead: list[WebSocket] = []
        for ws in self.active[session_id]:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_id, ws)

    async def send_heartbeat(self, session_id: str) -> None:
        await self.broadcast(
            session_id,
            {"type": "heartbeat", "message": "Connection alive"},
        )

    def is_connected(self, session_id: str) -> bool:
        return session_id in self.active


# Global singleton
manager = ConnectionManager()

__all__ = ["ConnectionManager", "manager"]
