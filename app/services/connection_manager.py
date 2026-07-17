from collections import defaultdict

from fastapi import WebSocket

USER_CHANNEL_PREFIX = "ws:user:"


class ConnectionManager:
    """Tracks this worker process's live WebSocket connections, per user.

    Only in-process state — a multi-worker deployment needs the Redis
    pub/sub bridge in app.services.ws_pubsub to reach a user connected to a
    *different* worker. See publish_to_user().
    """

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        connections = self._connections.get(user_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            self._connections.pop(user_id, None)

    async def send_local(self, user_id: int, message: dict) -> bool:
        """Delivers to any local connections for user_id. Returns whether
        anyone was actually connected here to receive it."""
        connections = self._connections.get(user_id)
        if not connections:
            return False
        for websocket in list(connections):
            await websocket.send_json(message)
        return True

    def is_connected_locally(self, user_id: int) -> bool:
        return bool(self._connections.get(user_id))


manager = ConnectionManager()
