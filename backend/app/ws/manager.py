from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        await websocket.accept()
        self._connections.setdefault(channel, set()).add(websocket)

    async def disconnect(self, websocket: WebSocket, channel: str) -> None:
        self._connections.get(channel, set()).discard(websocket)

    async def broadcast(self, channel: str, data: dict) -> None:
        # Iterate over a snapshot copy — other coroutines may add/remove during awaits
        dead = set()
        for ws in set(self._connections.get(channel, set())):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self._connections.get(channel, set()).difference_update(dead)

    def connection_count(self, channel: str) -> int:
        return len(self._connections.get(channel, set()))


ws_manager = ConnectionManager()
