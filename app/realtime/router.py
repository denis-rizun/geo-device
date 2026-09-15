from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await subscriber.detach(connection)
