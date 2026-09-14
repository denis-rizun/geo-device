"""location_pings

Revision ID: 0003_location_pings
Revises: 0002_geozones
Create Date: 2026-09-14

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "location_pings",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column(
            "point",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeogFromText",
                name="geography",
            ),
            nullable=False,
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_location_pings"),
    )
    op.create_index("ix_pings_device_recorded", "location_pings", ["device_id", "recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_pings_device_recorded", table_name="location_pings")
    op.drop_table("location_pings")
