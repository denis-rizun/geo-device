# Geo device

Real-time geo-tracking alerting service

- **Backend** — Python 3.14, FastAPI, SQLAlchemy 2 (async), Alembic
- **Storage** — PostgreSQL 17 + PostGIS 3.5, Redis 7 (ingest stream + pub/sub + alert state)
- **Frontend** — one static Leaflet page, served by the app itself


## Run with Docker

```bash
cp .env.example .env
docker compose up --build -d
```

- API — <http://localhost:8000>
- Swagger — <http://localhost:8000/docs>
- Demo map — <http://localhost:8000/api/v1/ui/>

## Load generator

Simulated devices drift around a center and report through the real HTTP ingest endpoint

```bash
uv sync
uv run python generator.py
uv run python generator.py --devices 2000 --interval 1
```

| Flag         | Default                              | Meaning                               |
|--------------|--------------------------------------|---------------------------------------|
| `--url`      | `http://localhost:8000/ingest/batch` | Ingest endpoint                       |
| `--devices`  | 10000                                | Simulated devices                     |
| `--interval` | 3.0                                  | Seconds between reports of one device |
| `--drift`    | 0.0005                               | Max degrees moved per tick            |

Batch size (500 pings per request) and in-flight request concurrency (16) are constants in the script.

One line per tick:

```
tick    1 |  0.42s | accepted   9500 | pings/s    22619 | rejected     0 | failed     0
```

| Field      | Meaning                                                                             |
|------------|-------------------------------------------------------------------------------------|
| `accepted` | Pings the API answered `202` for                                                    |
| `pings/s`  | `accepted / tick duration` — burst rate; sustained load is `--devices / --interval` |
| `rejected` | Pings refused with `503` because the ingest backlog was full                        |
| `failed`   | Pings lost to transport errors or an unexpected status                              |

## API

Every REST call identifies the user with the `X-User-ID` header. Geozones are strictly isolated per user.

| Method   | Path              | Purpose                                                                                     |
|----------|-------------------|---------------------------------------------------------------------------------------------|
| `POST`   | `/ingest/batch`   | Ingest a batch of device locations (`202`, or `503 + Retry-After` when the backlog is full) |
| `POST`   | `/geozones`       | Create a zone: `name`, `lat`, `lon`, `radius_m`                                             |
| `GET`    | `/geozones`       | List own zones (`limit`, `offset`)                                                          |
| `GET`    | `/geozones/{id}`  | Retrieve one                                                                                |
| `PATCH`  | `/geozones/{id}`  | Update name, center or radius                                                               |
| `DELETE` | `/geozones/{id}`  | Delete                                                                                      |
| `GET`    | `/health`         | Liveness                                                                                    |
| `WS`     | `/ws?user_id=...` | Live positions and alerts                                                                   |

### WebSocket protocol

```jsonc
// every ~1s, only the devices that reported in that window: [device_id, lat, lon, recorded_at]
{"type": "device_positions", "positions": [["dev-00001", 50.4501, 30.5234, "2026-09-15T08:00:00+00:00"]]}

// when a device enters one of this user's zones
{"type": "geozone_alert", "alerts": [{
  "user_id": "alice", "geozone_id": 7, "geozone_name": "warehouse",
  "device_id": "dev-00001", "lat": 50.4501, "lon": 30.5234,
  "recorded_at": "2026-09-15T08:00:00+00:00"
}]}
```

## Architecture

Request flow at a glance: [`docs/architecture.excalidraw`](docs/architecture.excalidraw) (open in <https://excalidraw.com>).

### Ingest path and high throughput

```
device → POST /ingest/batch → Redis Stream "pings" → consumer group → ingest workers
                                                                          ├→ bulk INSERT into location_pings
                                                                          ├→ ST_DWithin match → alerts:{user_id}
                                                                          └→ 1s position snapshot → positions
```

```
app/
  core/            config, db, logging, redis client, shared types
  domains/         devices (ingest) and geozones (CRUD)
  pipeline/        redis stream wrapper, ingest workers, matcher, alert suppression
  realtime/        websocket registry, pub/sub subscriber, event publishers
generator.py       load generator (10k devices)
migrations/        alembic revisions
frontend/          Leaflet demo UI
```

## Configuration

All settings come from `.env` (see `.env.example`);

| Variable                                       | Default  | Meaning                                                      |
|------------------------------------------------|----------|--------------------------------------------------------------|
| `INGEST_WORKERS`                               | 4        | Stream consumers per process; bounds the DB connection usage |
| `INGEST_CHUNK_SIZE`                            | 500      | Pings per stream entry                                       |
| `INGEST_MAX_HTTP_BATCH_SIZE`                   | 1000     | Hard cap on one ingest request                               |
| `INGEST_BACKLOG_LIMIT`                         | 10000    | Backlog above which ingest answers `503`                     |
| `INGEST_STREAM_MAX_LEN`                        | 1000000  | Stream trim length                                           |
| `INGEST_DRAIN_TIMEOUT_S`                       | 10       | Shutdown drain budget                                        |
| `INGEST_ZONE_ENTRY_TTL_S`                      | 60       | How long a device stays "inside" without reporting           |
| `INGEST_POSITION_FLUSH_INTERVAL_S`             | 1.0      | Live-map snapshot period                                     |
| `REALTIME_QUEUE_SIZE`                          | 64       | Per-connection send queue                                    |
| `POSTGRES_POOL_SIZE` / `POSTGRES_MAX_OVERFLOW` | 20 / 200 | SQLAlchemy pool                                              |
