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

_SET_BOUNDS = """
CREATE OR REPLACE FUNCTION geozones_set_bounds() RETURNS trigger AS $$
DECLARE
    env geometry;
BEGIN
    -- padded by 1% + 1 m so the envelope is always a superset of the exact ST_DWithin circle
    env := ST_Envelope(ST_Buffer(NEW.center, NEW.radius_m * 1.01 + 1.0)::geometry);

    -- a buffer wrapping the antimeridian comes back as a near-global box with a gap at +/-180
    IF ST_XMax(env) - ST_XMin(env) > 350.0 THEN
        env := ST_MakeEnvelope(-180.0, ST_YMin(env), 180.0, ST_YMax(env), 4326);
    END IF;

    NEW.bounds := env;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(_SET_BOUNDS)
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
            "bounds",
            geoalchemy2.types.Geometry(
                geometry_type="POLYGON",
                srid=4326,
                spatial_index=False,
            ),
            nullable=False,
        ),
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
    op.execute("""
        CREATE TRIGGER trg_geozones_set_bounds
        BEFORE INSERT OR UPDATE OF center, radius_m ON geozones
        FOR EACH ROW EXECUTE FUNCTION geozones_set_bounds()
    """)
    op.create_index("ix_geozones_center_gist", "geozones", ["center"], postgresql_using="gist")
    op.create_index("ix_geozones_bounds_gist", "geozones", ["bounds"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_index("ix_geozones_bounds_gist", table_name="geozones")
    op.drop_index("ix_geozones_center_gist", table_name="geozones")
    op.drop_table("geozones")
    op.execute("DROP FUNCTION IF EXISTS geozones_set_bounds()")
