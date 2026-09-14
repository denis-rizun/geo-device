from datetime import datetime

from geoalchemy2 import Geography
from geoalchemy2.elements import WKBElement
from sqlalchemy import BigInteger, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LocationPing(Base):
    __tablename__ = "location_pings"
    __table_args__ = (Index("ix_pings_device_recorded", "device_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64))
    point: Mapped[WKBElement] = mapped_column(Geography(geometry_type="POINT", srid=4326, spatial_index=False))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
