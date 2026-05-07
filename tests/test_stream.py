"""Tests for vcmix.stream module."""
import io
import json

from vcmix.stream.emitter import DataStream, StreamEvent


class TestStreamEvent:
    def test_to_dict(self):
        e = StreamEvent(
            event_type="track_level",
            timestamp_ms=100.0,
            track="vocal",
            data={"rms_db": -12.3},
        )
        d = e.to_dict()
        assert d["type"] == "track_level"
        assert d["track"] == "vocal"
        assert d["rms_db"] == -12.3

    def test_to_json(self):
        e = StreamEvent(
            event_type="warning",
            timestamp_ms=50.0,
            track="vocal",
            data={"msg": "clip"},
        )
        j = e.to_json()
        parsed = json.loads(j)
        assert parsed["type"] == "warning"


class TestDataStreamJSON:
    def test_track_level_emits_json(self):
        buf = io.StringIO()
        ds = DataStream(format="json", output=buf)
        ds.start()
        ds.emit_track_level("vocal", rms_db=-12.3, peak_db=-3.2)
        line = buf.getvalue().strip()
        parsed = json.loads(line)
        assert parsed["type"] == "track_level"
        assert parsed["track"] == "vocal"

    def test_warning_emits_json(self):
        buf = io.StringIO()
        ds = DataStream(format="json", output=buf)
        ds.start()
        ds.emit_warning("vocal", "clipping", "Peak too high")
        line = buf.getvalue().strip()
        parsed = json.loads(line)
        assert parsed["type"] == "warning"
        assert parsed["level"] == "warning"


class TestDataStreamDict:
    def test_accumulates_events(self):
        ds = DataStream(format="dict")
        ds.start()
        ds.emit_track_level("vocal", rms_db=-12, peak_db=-3)
        ds.emit_master_level(rms_db=-10, peak_db=-2)
        events = ds.get_events()
        assert len(events) == 2

    def test_latest_levels(self):
        ds = DataStream(format="dict")
        ds.start()
        ds.emit_track_level("vocal", rms_db=-12, peak_db=-3)
        ds.emit_track_level("bgv", rms_db=-18, peak_db=-6)
        levels = ds.get_latest_levels()
        assert "vocal" in levels
        assert "bgv" in levels


class TestDataStreamCallback:
    def test_callback_called(self):
        received = []
        ds = DataStream(
            format="callback",
            callback=lambda e: received.append(e),
        )
        ds.start()
        ds.emit_track_level("vocal", rms_db=-12, peak_db=-3)
        assert len(received) == 1
        assert received[0].track == "vocal"
