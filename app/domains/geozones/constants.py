MAX_RADIUS_M = 100_000.0
MAX_NAME_LENGTH = 128

BOUNDS_FUNCTION = "geozones_set_bounds"
BOUNDS_TRIGGER = "trg_geozones_set_bounds"

CREATE_BOUNDS_FUNCTION = f"""
CREATE OR REPLACE FUNCTION {BOUNDS_FUNCTION}() RETURNS trigger AS $$
DECLARE
    env geometry;
BEGIN
    -- padded by 1 percent + 1 m so the envelope is always a superset of the exact ST_DWithin circle
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

CREATE_BOUNDS_TRIGGER = f"""
CREATE TRIGGER {BOUNDS_TRIGGER}
BEFORE INSERT OR UPDATE OF center, radius_m ON geozones
FOR EACH ROW EXECUTE FUNCTION {BOUNDS_FUNCTION}()
"""

DROP_BOUNDS_FUNCTION = f"DROP FUNCTION IF EXISTS {BOUNDS_FUNCTION}()"
