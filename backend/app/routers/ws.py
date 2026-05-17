import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ws.manager import ws_manager

router = APIRouter()

VALID_CHANNELS = {"signals", "trades", "portfolio", "prices", "live_trades"}

_PING_INTERVAL = 25  # seconds — below typical LB idle-timeout of 60s


@router.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    if channel not in VALID_CHANNELS:
        await websocket.close(code=4004)
        return
    await ws_manager.connect(websocket, channel)
    try:
        while True:
            # Wait for client message with timeout; send ping on timeout to keep
            # the connection alive through load-balancer idle-timeout windows.
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=_PING_INTERVAL)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except (WebSocketDisconnect, Exception):
        await ws_manager.disconnect(websocket, channel)
