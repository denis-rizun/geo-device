from datetime import datetime

from geoalchemy2.elements import WKBElement
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.utils import GEOGRAPHY_POINT
from app.domains.geozones.constants import MAX_NAME_LENGTH, MAX_RADIUS_M


class Geozone(Base):
    __tablename__ = "geozones"
    __table_args__ = (
        CheckConstraint(
            f"radius_m > 0 AND radius_m <= {MAX_RADIUS_M}",
            name="ck_geozones_radius_range",
        ),
        UniqueConstraint("user_id", "name", name="uq_geozones_user_name"),
        Index("ix_geozones_center_gist", "center", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(MAX_NAME_LENGTH))
    center: Mapped[WKBElement] = mapped_column(GEOGRAPHY_POINT)
    radius_m: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
