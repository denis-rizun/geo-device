from datetime import UTC, datetime

import orjson
import pytest

from app.pipeline.constants import PAYLOAD_FIELD
from app.pipeline.utils import Ping, decode_pings, encode_pings, parse_stream_chunk

pytestmark = pytest.mark.unit

RECORDED_AT = datetime(2026, 9, 15, 12, 30, 45, tzinfo=UTC)


class TestPing:
    def test_to_json_serialises_recorded_at_as_isoformat(self) -> None:
        ping = Ping(device_id="dev-1", lat=50.45, lon=30.52, recorded_at=RECORDED_AT)

        assert ping.to_json() == ("dev-1", 50.45, 30.52, "2026-09-15T12:30:45+00:00")

    def test_from_json_restores_the_original_ping(self) -> None:
        ping = Ping(device_id="dev-1", lat=50.45, lon=30.52, recorded_at=RECORDED_AT)

        assert Ping.from_json(ping.to_json()) == ping


class TestEncodePings:
    def test_round_trip_preserves_every_ping(self) -> None:
        pings = [
            Ping(device_id="dev-1", lat=50.45, lon=30.52, recorded_at=RECORDED_AT),
            Ping(device_id="dev-2", lat=-33.86, lon=151.2, recorded_at=RECORDED_AT),
        ]

        assert decode_pings(encode_pings(pings)) == pings

    def test_encodes_an_empty_batch(self) -> None:
        assert decode_pings(encode_pings([])) == []


class TestParseStreamChunk:
    def test_parses_every_entry_with_a_payload(self) -> None:
        pings = [Ping(device_id="dev-1", lat=1.0, lon=2.0, recorded_at=RECORDED_AT)]
        entries = [(b"1-0", {PAYLOAD_FIELD: encode_pings(pings)})]

        chunks = parse_stream_chunk(entries)

        assert [(chunk.entry_id, chunk.pings) for chunk in chunks] == [(b"1-0", pings)]

    def test_skips_entries_without_a_payload(self) -> None:
        pings = [Ping(device_id="dev-1", lat=1.0, lon=2.0, recorded_at=RECORDED_AT)]
        entries = [
            (b"1-0", {}),
            (b"2-0", {PAYLOAD_FIELD: b""}),
            (b"3-0", {PAYLOAD_FIELD: encode_pings(pings)}),
        ]

        chunks = parse_stream_chunk(entries)

        assert [chunk.entry_id for chunk in chunks] == [b"3-0"]

    def test_returns_nothing_for_no_entries(self) -> None:
        assert parse_stream_chunk([]) == []

    def test_reads_back_a_payload_written_as_raw_json(self) -> None:
        raw = orjson.dumps([["dev-1", 1.0, 2.0, RECORDED_AT.isoformat()]])

        chunks = parse_stream_chunk([(b"1-0", {PAYLOAD_FIELD: raw})])

        assert chunks[0].pings == [Ping(device_id="dev-1", lat=1.0, lon=2.0, recorded_at=RECORDED_AT)]
