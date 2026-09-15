CREATE_BOUNDS_FUNCTION = """
CREATE OR REPLACE FUNCTION geozones_set_bounds() RETURNS trigger AS $$
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

CREATE_BOUNDS_TRIGGER = """
CREATE TRIGGER trg_geozones_set_bounds
BEFORE INSERT OR UPDATE OF center, radius_m ON geozones
FOR EACH ROW EXECUTE FUNCTION geozones_set_bounds()
"""

DROP_BOUNDS_FUNCTION = "DROP FUNCTION IF EXISTS geozones_set_bounds()"
