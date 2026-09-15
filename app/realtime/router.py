from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime.constants import WS_DISCONNECT_TYPE
from app.realtime.dependencies import SubscriberDep, WSUserDep
from app.realtime.registry import Connection

router = APIRouter(tags=["Realtime"])


@router.websocket("/ws")
async def stream_updates(websocket: WebSocket, user_id: WSUserDep, subscriber: SubscriberDep) -> None:
    await websocket.accept()
    connection = Connection(websocket, user_id)
    await subscriber.attach(connection)
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == WS_DISCONNECT_TYPE:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await subscriber.detach(connection)
