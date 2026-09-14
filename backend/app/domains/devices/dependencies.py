from typing import Annotated

from fastapi import Depends

from app.dependencies import RedisDep
from app.domains.devices.service import DeviceService


def get_device_service(redis: RedisDep) -> DeviceService:
    return DeviceService(redis)


DeviceServiceDep = Annotated[DeviceService, Depends(get_device_service)]
