from typing import Any

from fastapi import APIRouter, status

from app.domains.devices.dependencies import DeviceServiceDep
from app.domains.devices.schemas import LocationAcceptedResponse, LocationBatchRequest

_BACKLOG_FULL: dict[int | str, dict[str, Any]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "description": "Ingest backlog is full, retry later",
        "headers": {
            "Retry-After": {
                "description": "Seconds to wait before retrying the batch",
                "schema": {"type": "integer"},
            }
        },
    }
}

router = APIRouter(prefix="/ingest", tags=["Devices"])


@router.post(
    path="/batch",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a batch of device locations",
    responses=_BACKLOG_FULL,
)
async def ingest_batch(payload: LocationBatchRequest, service: DeviceServiceDep) -> LocationAcceptedResponse:
    return await service.save_points(payload)
