from typing import Annotated

from fastapi import Depends, Query, WebSocketException

from app.core.utils import MAX_ID_LENGTH
from app.realtime.constants import CLOSE_INVALID_USER
from app.realtime.subscriber import Subscriber, get_subscriber


async def get_ws_user(user_id: Annotated[str | None, Query()] = None) -> str:
    resolved = (user_id or "").strip()
    if not resolved or len(resolved) > MAX_ID_LENGTH:
        raise WebSocketException(code=CLOSE_INVALID_USER, reason="user_id query parameter is incorrect")

    return resolved


SubscriberDep = Annotated[Subscriber, Depends(get_subscriber)]
WSUserDep = Annotated[str, Depends(get_ws_user)]
