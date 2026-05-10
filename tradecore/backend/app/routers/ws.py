from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ws.manager import ws_manager

router = APIRouter()

VALID_CHANNELS = {"signals", "trades", "portfolio"}


@router.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    if channel not in VALID_CHANNELS:
        await websocket.close(code=4004)
        return
    await ws_manager.connect(websocket, channel)
    try:
        while True:
            # Keep alive — client can send pings; we just discard them
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, channel)
