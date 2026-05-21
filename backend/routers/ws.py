"""WebSocket router — real-time node streaming and market tick endpoints."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.market_hours import get_market_status
from backend.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/analyze/{session_id}")
async def ws_analyze(websocket: WebSocket, session_id: str) -> None:
    """Stream node events for a running pipeline session."""
    await manager.connect(session_id, websocket)

    try:
        await websocket.send_json(
            {
                "type": "connected",
                "session_id": session_id,
                "market_status": get_market_status(),
                "message": "Connected to MarketPulse India stream",
            }
        )

        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0,
                )
                if data == "ping":
                    await websocket.send_json({"type": "pong", "message": "pong"})
            except TimeoutError:
                await manager.send_heartbeat(session_id)

    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
    except Exception as exc:
        logger.debug("ws_analyze error on session %s: %s", session_id, exc)
        manager.disconnect(session_id, websocket)


@router.websocket("/ws/market")
async def ws_market(websocket: WebSocket) -> None:
    """Push Nifty + market status ticks every 60 seconds."""
    await websocket.accept()
    try:
        while True:
            from mcp_servers.yfinance_india.server import get_index_data  # local import

            data: dict[str, object] = await asyncio.to_thread(get_index_data)
            data["market_status"] = get_market_status()
            await websocket.send_json(
                {
                    "type": "market_update",
                    "data": data,
                }
            )
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("ws_market error: %s", exc)


__all__ = ["router"]
