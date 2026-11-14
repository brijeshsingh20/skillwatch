"""Edge agent: payloads, persistent queue, retry/backoff, idempotency, outage recovery."""
import json
import random
from datetime import date, datetime, timezone

import pytest

from scripts.generate_demo_footage import generate_centre
from scripts.scenario import SCENARIO
from vision.lowbw import (
    EdgeConfig, EdgeQueue, TransportError, Uploader, build_item, build_offline_item, encode_batch, new_ingest_id, run_once,
)
from vision.config import load_config


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class FakeServer:
    """Stand-in for the ingest endpoint. `mode` flips between outage, ok, auth failure, etc."""

    def __init__(self):
        self.mode = "ok"
        self.seen: set[str] = set()
        self.calls = 0
        self.last_body = b""

    def send(self, body):
        self.calls += 1
        self.last_body = body
        if self.mode == "down":
            raise TransportError("no route to host")
        if self.mode == "auth":
            return 401, {"detail": "bad key"}
        if self.mode == "busy":
            return 503, {}
        items = json.loads(body)["observations"]
        results = []
        for it in items:
            if it.get("estimated_count") == -1:
                results.append({"ingest_id": it["ingest_id"], "status": "rejected", "error": "Unknown centre"})
            elif it["ingest_id"] in self.seen:
                results.append({"ingest_id": it["ingest_id"], "status": "duplicate"})
            else:
                self.seen.add(it["ingest_id"])
                results.append({"ingest_id": it["ingest_id"], "status": "created"})
        return 200, {"results": results}


def item(n=5, centre="SC001"):
    return {"kind": "observation", "ingest_id": new_ingest_id(), "centre_code": centre, "captured_at": "2026-11-10T09:00:00+00:00",
            "session_date": "2026-11-10", "estimated_count": n, "items_detected": {"chair": 3}, "items_not_operable": {},
            "confidence": 0.9, "frame_quality": 1.0, "low_quality": False}


@pytest.fixture()
def rig():
    clock = Clock()
    q = EdgeQueue(":memory:", max_items=5, clock=clock)
    server = FakeServer()
    up = Uploader(q, server, batch_size=3, rng=random.Random(1))
    return clock, q, server, up


def test_happy_path_empties_queue(rig):
    clock, q, server, up = rig
    for _ in range(4):
        q.enqueue(item(), b"\xff\xd8\xff fake jpeg")
    report = up.flush()
    assert (report.sent, report.remaining, report.error) == (4, 0, None)
    assert server.calls == 2  # batches of 3 + 1


def test_outage_keeps_items_and_backs_off_then_recovers(rig):
    clock, q, server, up = rig
    q.enqueue(item(), b"x")
    server.mode = "down"
    r1 = up.flush()
    assert r1.failed == 1 and r1.remaining == 1 and "unreachable" in r1.error
    assert up.flush().failed == 0 and server.calls == 1   # still inside the backoff window: no hammering
    clock.t += 3600                                          # time passes
    server.mode = "ok"
    r2 = up.flush()
    assert r2.sent == 1 and r2.remaining == 0


def test_backoff_grows_with_attempts():
    up = Uploader(EdgeQueue(":memory:"), FakeServer(), base_backoff_s=30, max_backoff_s=600, rng=random.Random(0))
    delays = [up._delay(n) for n in range(0, 8)]
    assert delays[1] > delays[0] and max(delays) <= 600 * 1.2


def test_queue_survives_restart(tmp_path):
    path = tmp_path / "q.db"
    q = EdgeQueue(path)
    q.enqueue(item(7), b"thumb")
    q.close()
    again = EdgeQueue(path)
    rows = again.due(10)
    assert len(rows) == 1 and rows[0].item["estimated_count"] == 7 and rows[0].thumb == b"thumb"


def test_duplicate_enqueue_is_ignored_and_server_duplicates_dropped(rig):
    clock, q, server, up = rig
    it = item()
    q.enqueue(it, None)
    q.enqueue(it, None)
    assert q.pending() == 1
    up.flush()
    q.enqueue(it, None)           # same ingest_id re-queued after a crash-before-ack
    assert up.flush().duplicates == 1 and q.pending() == 0


def test_rejected_items_go_to_dead_letter_and_do_not_block_others(rig):
    clock, q, server, up = rig
    q.enqueue(item(-1), None)
    q.enqueue(item(4), None)
    report = up.flush()
    assert report.rejected == 1 and report.sent == 1 and q.stats()["dead"] == 1 and q.pending() == 0


def test_bad_api_key_stops_cleanly(rig):
    clock, q, server, up = rig
    q.enqueue(item(), None)
    server.mode = "auth"
    report = up.flush()
    assert "API key" in report.error and q.pending() == 1


def test_server_busy_is_retried_later(rig):
    clock, q, server, up = rig
    q.enqueue(item(), None)
    server.mode = "busy"
    assert up.flush().failed == 1 and q.pending() == 1


def test_queue_is_bounded_and_oldest_dropped_to_audit_table(rig):
    clock, q, server, up = rig
    for n in range(8):
        q.enqueue(item(n), None)
    assert q.pending() == 5 and q.stats()["dead"] == 3


def test_counts_only_mode_is_much_smaller(rig):
    clock, q, server, up = rig
    q.enqueue(item(), b"\xff\xd8\xff" + b"0" * 5000)
    rows = q.due(1)
    assert len(encode_batch(rows, include_thumbnails=False)) < 800 < len(encode_batch(rows, include_thumbnails=True))


def test_offline_event_payload():
    it = build_offline_item("SC001", "stream timeout", datetime.now(timezone.utc), new_ingest_id())
    assert it["kind"] == "camera_offline" and it["reason"] == "stream timeout"


@pytest.fixture(scope="module")
def demo_data(tmp_path_factory):
    root = tmp_path_factory.mktemp("lowbw")
    for sc in SCENARIO:
        generate_centre(sc, root, duration_s=24, fps=8)
    return root


def test_real_pipeline_payload_is_small_and_complete(demo_data, tmp_path):
    cfg = EdgeConfig("SC002", data_dir=str(demo_data), queue_path=str(tmp_path / "q.db"))
    server = FakeServer()
    sent_item, report = run_once(cfg, transport=server)
    assert report.sent == 1 and report.remaining == 0
    body = server.last_body
    obs = json.loads(body)["observations"][0]
    assert obs["centre_code"] == "SC002" and abs(obs["estimated_count"] - 8) <= 1
    assert obs["thumbnail_b64"] and len(body) < 15_000          # counts + one tiny thumbnail, nothing else
    assert b"video" not in body.lower().replace(b"kind", b"")      # no video reference leaks into the payload


def test_missing_video_queues_camera_offline_event(demo_data, tmp_path):
    cfg = EdgeConfig("SC001", data_dir=str(demo_data), queue_path=str(tmp_path / "q2.db"))
    server = FakeServer()
    sent_item, _ = run_once(cfg, video=demo_data / "videos" / "missing.mp4", transport=server)
    assert sent_item["kind"] == "camera_offline"


def test_outage_during_run_is_recovered_by_later_flush(demo_data, tmp_path):
    cfg = EdgeConfig("SC003", data_dir=str(demo_data), queue_path=str(tmp_path / "q3.db"))
    server = FakeServer()
    server.mode = "down"
    _, report = run_once(cfg, transport=server)
    assert report.remaining == 1 and report.error
    q = EdgeQueue(cfg.queue_path)
    q.db.execute("UPDATE queue SET next_try_at=0"); q.db.commit()
    server.mode = "ok"
    assert Uploader(q, server).flush().sent == 1


def test_lowbw_profile_values():
    cfg = load_config("lowbw")
    assert cfg.width == 320 and cfg.jpeg_quality == 50 and cfg.frame_interval_s == 4.0


def test_worker_runs_all_centres_every_cycle_and_sleeps_between(demo_data, tmp_path):
    from dataclasses import replace
    from vision.lowbw import run_worker

    template = EdgeConfig("SC001", data_dir=str(demo_data), queue_path=str(tmp_path / "w.db"))
    server, sleeps = FakeServer(), []
    cycles = run_worker(["SC001", "SC002"], template, interval_min=5, cycles=2, transport=server, sleep=sleeps.append)
    assert cycles == 2 and len(server.seen) == 4 and sleeps == [300]


def test_worker_survives_a_crash_at_one_centre(demo_data, tmp_path):
    from vision.lowbw import run_worker

    class Flaky(FakeServer):
        def send(self, body):
            if self.calls == 0:
                self.calls += 1
                raise RuntimeError("boom")      # not a TransportError: simulates an unexpected bug
            return super().send(body)

    template = EdgeConfig("SC001", data_dir=str(demo_data), queue_path=str(tmp_path / "w2.db"))
    server = Flaky()
    assert run_worker(["SC001", "SC002"], template, 1, cycles=1, transport=server, sleep=lambda s: None) == 1
    assert len(server.seen) >= 1          # the second centre was still processed
