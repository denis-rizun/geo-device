import argparse
import asyncio
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import batched
from time import monotonic

import httpx

DEFAULT_URL = "http://localhost:8000/ingest/batch"
CENTER = (50.4501, 30.5234)
SPREAD = 0.15
BATCH_SIZE = 500
CONCURRENCY = 16
REQUEST_TIMEOUT_S = 30.0


@dataclass(slots=True)
class Device:
    device_id: str
    lat: float
    lon: float

    def drift(self, delta: float) -> None:
        self.lat += random.uniform(-delta, delta)
        self.lon += random.uniform(-delta, delta)

    def to_payload(self, recorded_at: str) -> dict[str, str | float]:
        return {"device_id": self.device_id, "lat": self.lat, "lon": self.lon, "recorded_at": recorded_at}


@dataclass(slots=True)
class TickStats:
    accepted: int = 0
    rejected: int = 0
    failed: int = 0

    def merge(self, other: TickStats) -> None:
        self.accepted += other.accepted
        self.rejected += other.rejected
        self.failed += other.failed


def build_devices(count: int) -> list[Device]:
    lat, lon = CENTER
    return [
        Device(
            device_id=f"dev-{index:05d}",
            lat=lat + random.uniform(-SPREAD, SPREAD),
            lon=lon + random.uniform(-SPREAD, SPREAD),
        )
        for index in range(count)
    ]


async def send_batch(
    client: httpx.AsyncClient,
    url: str,
    devices: tuple[Device, ...],
    semaphore: asyncio.Semaphore,
) -> TickStats:
    stats = TickStats()
    recorded_at = datetime.now(UTC).isoformat()
    payload = {"points": [device.to_payload(recorded_at) for device in devices]}

    async with semaphore:
        try:
            response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            stats.failed += len(devices)
            print(f"request failed: {exc}")
            return stats

    if response.is_success:
        stats.accepted += len(devices)
    elif response.status_code == httpx.codes.SERVICE_UNAVAILABLE:
        stats.rejected += len(devices)
    else:
        stats.failed += len(devices)
        print(f"unexpected response {response.status_code}: {response.text[:200]}")

    return stats


async def run_tick(
    client: httpx.AsyncClient,
    url: str,
    devices: list[Device],
    drift: float,
    semaphore: asyncio.Semaphore,
) -> TickStats:
    for device in devices:
        device.drift(drift)

    results = await asyncio.gather(
        *(send_batch(client, url, chunk, semaphore) for chunk in batched(devices, BATCH_SIZE, strict=False))
    )

    total = TickStats()
    for result in results:
        total.merge(result)

    return total


async def generate(args: argparse.Namespace) -> None:
    devices = build_devices(args.devices)
    semaphore = asyncio.Semaphore(CONCURRENCY)
    limits = httpx.Limits(max_connections=CONCURRENCY, max_keepalive_connections=CONCURRENCY)

    print(f"generating {args.devices} devices -> {args.url} every {args.interval}s")

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S, limits=limits) as client:
        tick = 0
        while True:
            tick += 1
            started = monotonic()
            stats = await run_tick(client, args.url, devices, args.drift, semaphore)
            elapsed = monotonic() - started

            print(
                f"tick {tick:>4} | {elapsed:5.2f}s | accepted {stats.accepted:>6} "
                f"| pings/s {stats.accepted / elapsed if elapsed else 0:>8.0f} "
                f"| rejected {stats.rejected:>5} | failed {stats.failed:>5}"
            )

            await asyncio.sleep(max(0.0, args.interval - elapsed))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate tracking devices reporting their location.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--devices", type=int, default=10_000)
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--drift", type=float, default=0.0005)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(generate(args))
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
