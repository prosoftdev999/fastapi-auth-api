import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.auth.dependencies import get_current_user_ws
from app.models.user import User
from app.services.connection_manager import manager
from app.services.ws_pubsub import publish_to_user

logger = logging.getLogger("app.websocket")

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    current_user: User = Depends(get_current_user_ws),
) -> None:
    """One socket per connected client, multiplexed by message `type`.

    Client -> server:
      {"type": "message", "to": <user_id>, "body": "..."}   private message

    Server -> client:
      {"type": "message", "from": <user_id>, "body": "..."}
      {"type": "notification", "body": "..."}                pushed by other
                                                               parts of the
                                                               app, e.g. an
                                                               admin role change
      {"type": "error", "detail": "..."}
    """
    await manager.connect(current_user.id, websocket)

    try:
        while True:
            data = await websocket.receive_json()

            if not isinstance(data, dict) or data.get("type") != "message":
                await websocket.send_json(
                    {"type": "error", "detail": "Unsupported message type"}
                )
                continue

            recipient_id = data.get("to")
            body = data.get("body")

            if not isinstance(recipient_id, int) or not isinstance(body, str):
                await websocket.send_json(
                    {
                        "type": "error",
                        "detail": "'to' must be an integer user id and 'body' a string",
                    }
                )
                continue

            await publish_to_user(
                recipient_id,
                {"type": "message", "from": current_user.id, "body": body},
            )
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(current_user.id, websocket)
