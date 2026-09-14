"""geozones

Revision ID: 0002_geozones
Revises: 0001_enable_postgis
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "geozones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "center",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeogFromText",
                name="geography",
            ),
            nullable=False,
        ),
        sa.Column("radius_m", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("radius_m > 0 AND radius_m <= 100000.0", name="ck_geozones_radius_range"),
        sa.PrimaryKeyConstraint("id", name="pk_geozones"),
        sa.UniqueConstraint("user_id", "name", name="uq_geozones_user_name"),
    )
    op.create_index("ix_geozones_center_gist", "geozones", ["center"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_index("ix_geozones_center_gist", table_name="geozones")
    op.drop_table("geozones")
