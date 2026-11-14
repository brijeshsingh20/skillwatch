"""Low-bandwidth edge agent: analyse locally, upload only counts + one tiny pixelated thumbnail.

* Raw video never leaves the centre. Each observation is ~6-9 KB (JSON + base64 JPEG), or <1 KB counts-only.
* Observations wait in a persistent SQLite queue and are retried with exponential backoff, so a dead link
  (power cut, no signal) loses nothing. Every item carries an ingest_id, so retries never double-count.
* Stdlib only for transport (urllib), so the edge box needs nothing beyond this repo's `vision/` package.

CLI:
  python -m vision.lowbw run --centre SC002 --server http://127.0.0.1:8000 --api-key KEY
  python -m vision.lowbw flush --server ... --api-key KEY
  python -m vision.lowbw status
  python -m vision.lowbw worker --interval-min 5      # simulated live feed for every centre
"""
import argparse
import base64
import json
import logging
import os
import random
import sqlite3
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

log = logging.getLogger("vision.lowbw")


# ---------------------------------------------------------------- payloads
def new_ingest_id() -> str:
    return uuid.uuid4().hex


def build_item(result, centre_code: str, session_date: date, captured_at: datetime, ingest_id: str) -> dict:
    """Compact observation record (no image). `result` is a vision PipelineResult."""
    return {
        "kind": "observation", "ingest_id": ingest_id, "centre_code": centre_code,
        "captured_at": captured_at.astimezone(timezone.utc).isoformat(), "session_date": session_date.isoformat(),
        "estimated_count": int(result.estimated_count), "items_detected": dict(result.items_detected),
        "items_not_operable": dict(result.items_not_operable), "confidence": float(result.confidence),
        "frame_quality": float(result.frame_quality), "low_quality": bool(result.low_quality),
    }


def build_offline_item(centre_code: str, reason: str, captured_at: datetime, ingest_id: str) -> dict:
    return {"kind": "camera_offline", "ingest_id": ingest_id, "centre_code": centre_code,
            "captured_at": captured_at.astimezone(timezone.utc).isoformat(), "reason": reason[:300]}


def encode_batch(rows: list["QueueRow"], include_thumbnails: bool = True) -> bytes:
    items = []
    for row in rows:
        item = dict(row.item)
        if include_thumbnails and row.thumb:
            item["thumbnail_b64"] = base64.b64encode(row.thumb).decode("ascii")
        items.append(item)
    return json.dumps({"observations": items}, separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------- queue
@dataclass
class QueueRow:
    id: int
    ingest_id: str
    item: dict
    thumb: bytes | None
    attempts: int


class EdgeQueue:
    """Persistent outbox (SQLite). Survives restarts and power cuts."""

    def __init__(self, path: str | Path = "data/edge_queue.db", max_items: int = 2000, clock: Callable[[], float] = time.time):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.max_items, self.clock = max_items, clock
        self.db = sqlite3.connect(str(path))
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS queue(
              id INTEGER PRIMARY KEY AUTOINCREMENT, ingest_id TEXT UNIQUE NOT NULL, item TEXT NOT NULL, thumb BLOB,
              created_at REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_try_at REAL NOT NULL DEFAULT 0,
              last_error TEXT);
            CREATE TABLE IF NOT EXISTS dead(
              id INTEGER PRIMARY KEY AUTOINCREMENT, ingest_id TEXT, item TEXT, reason TEXT, moved_at REAL);
        """)
        self.db.commit()

    def enqueue(self, item: dict, thumb: bytes | None = None) -> None:
        self.db.execute("INSERT OR IGNORE INTO queue(ingest_id, item, thumb, created_at) VALUES (?,?,?,?)",
                        (item["ingest_id"], json.dumps(item), thumb, self.clock()))
        overflow = self.pending() - self.max_items
        if overflow > 0:  # bounded disk use: the oldest items are sacrificed first, but kept in `dead` for audit
            old = [r[0] for r in self.db.execute("SELECT id FROM queue ORDER BY id LIMIT ?", (overflow,))]
            self.kill(old, "queue overflow: oldest observation dropped")
        self.db.commit()

    def due(self, limit: int) -> list[QueueRow]:
        cur = self.db.execute("SELECT id, ingest_id, item, thumb, attempts FROM queue WHERE next_try_at <= ? ORDER BY id LIMIT ?",
                              (self.clock(), limit))
        return [QueueRow(i, ing, json.loads(item), thumb, att) for i, ing, item, thumb, att in cur]

    def delete(self, ids: list[int]) -> None:
        self.db.executemany("DELETE FROM queue WHERE id=?", [(i,) for i in ids])
        self.db.commit()

    def fail(self, rows: list[QueueRow], error: str, delay_for: Callable[[int], float]) -> None:
        now = self.clock()
        self.db.executemany("UPDATE queue SET attempts=attempts+1, next_try_at=?, last_error=? WHERE id=?",
                            [(now + delay_for(r.attempts), error[:300], r.id) for r in rows])
        self.db.commit()

    def kill(self, ids: list[int], reason: str) -> None:
        for i in ids:
            self.db.execute("INSERT INTO dead(ingest_id, item, reason, moved_at) SELECT ingest_id, item, ?, ? FROM queue WHERE id=?",
                            (reason[:300], self.clock(), i))
        self.db.executemany("DELETE FROM queue WHERE id=?", [(i,) for i in ids])
        self.db.commit()

    def pending(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM queue").fetchone()[0]

    def stats(self) -> dict:
        nxt = self.db.execute("SELECT MIN(next_try_at) FROM queue").fetchone()[0]
        return {"pending": self.pending(), "dead": self.db.execute("SELECT COUNT(*) FROM dead").fetchone()[0],
                "next_retry_in_s": None if nxt is None else max(0, round(nxt - self.clock()))}

    def close(self) -> None:
        self.db.close()


# ---------------------------------------------------------------- transport + uploader
class TransportError(Exception):
    """Network-level failure: no usable HTTP response (offline, DNS, timeout, reset)."""


class Transport(Protocol):
    def send(self, body: bytes) -> tuple[int, dict]: ...


class HttpTransport:
    def __init__(self, server_url: str, api_key: str, timeout_s: float = 15.0):
        self.url = server_url.rstrip("/") + "/api/ingest/batch"
        self.api_key, self.timeout_s = api_key, timeout_s

    def send(self, body: bytes) -> tuple[int, dict]:
        req = urllib.request.Request(self.url, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "X-Ingest-Key": self.api_key})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:  # server answered with an error status
            try:
                return exc.code, json.loads(exc.read() or b"{}")
            except ValueError:
                return exc.code, {}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransportError(str(getattr(exc, "reason", exc))) from exc


@dataclass
class FlushReport:
    sent: int = 0
    duplicates: int = 0
    rejected: int = 0
    failed: int = 0
    remaining: int = 0
    error: str | None = None
    bytes_sent: int = 0


@dataclass
class Uploader:
    queue: EdgeQueue
    transport: Transport
    batch_size: int = 10
    send_thumbnails: bool = True
    base_backoff_s: float = 30.0
    max_backoff_s: float = 3600.0
    rng: random.Random = field(default_factory=random.Random)

    def _delay(self, attempts: int) -> float:
        return min(self.max_backoff_s, self.base_backoff_s * 2 ** attempts) * self.rng.uniform(0.8, 1.2)

    def _send(self, rows: list[QueueRow], report: FlushReport) -> bool:
        """Send one batch. Returns False when flushing should stop for now."""
        body = encode_batch(rows, self.send_thumbnails)
        try:
            status, data = self.transport.send(body)
        except TransportError as exc:
            self.queue.fail(rows, f"network: {exc}", self._delay)
            report.failed += len(rows)
            report.error = f"Server unreachable ({exc}). {len(rows)} item(s) kept for retry."
            return False
        report.bytes_sent += len(body)
        if status in (401, 403):
            self.queue.fail(rows, f"HTTP {status}", self._delay)
            report.failed += len(rows)
            report.error = f"Server refused the API key (HTTP {status}). Check INGEST_API_KEY."
            return False
        if status == 200:
            by_id = {r.ingest_id: r for r in rows}
            handled: set[str] = set()
            for res in data.get("results", []):
                row = by_id.get(res.get("ingest_id"))
                if row is None:
                    continue
                handled.add(row.ingest_id)
                if res.get("status") == "created":
                    self.queue.delete([row.id]); report.sent += 1
                elif res.get("status") == "duplicate":
                    self.queue.delete([row.id]); report.duplicates += 1
                else:
                    self.queue.kill([row.id], f"rejected by server: {res.get('error', 'unknown')}"); report.rejected += 1
            missing = [r for r in rows if r.ingest_id not in handled]
            if missing:
                self.queue.fail(missing, "missing from server response", self._delay)
                report.failed += len(missing)
            return True
        if 400 <= status < 500 and status != 429:
            if len(rows) > 1:  # one bad item must not block the good ones: retry them singly
                return all(self._send([r], report) for r in rows)
            self.queue.kill([rows[0].id], f"HTTP {status}: {json.dumps(data)[:200]}")
            report.rejected += 1
            return True
        self.queue.fail(rows, f"HTTP {status}", self._delay)  # 5xx / 429: try again later
        report.failed += len(rows)
        report.error = f"Server busy or failing (HTTP {status}). Will retry."
        return False

    def flush(self) -> FlushReport:
        report = FlushReport()
        while True:
            rows = self.queue.due(self.batch_size)
            if not rows or not self._send(rows, report):
                break
        report.remaining = self.queue.pending()
        return report


# ---------------------------------------------------------------- one analysis cycle
@dataclass(frozen=True)
class EdgeConfig:
    centre_code: str
    server_url: str = "http://127.0.0.1:8000"
    api_key: str = ""
    data_dir: str = "data"
    queue_path: str = "data/edge_queue.db"
    profile: str = "lowbw"
    send_thumbnail: bool = True
    batch_size: int = 10
    max_queue_items: int = 2000


def run_once(cfg: EdgeConfig, video: str | Path | None = None, transport: Transport | None = None,
             captured_at: datetime | None = None) -> tuple[dict, FlushReport]:
    """Analyse the centre's clip locally, queue the compact result, then try to upload the queue."""
    from vision.config import load_config
    from vision.infra_detector import Layout
    from vision.pipeline import analyse_video
    from vision.types import VideoError

    captured_at = captured_at or datetime.now(timezone.utc)
    data = Path(cfg.data_dir)
    queue = EdgeQueue(cfg.queue_path, cfg.max_queue_items)
    ingest_id = new_ingest_id()
    thumb: bytes | None = None
    try:
        vcfg = load_config(cfg.profile)
        layout = Layout.load(data / "layouts" / f"{cfg.centre_code}.json")
        with tempfile.TemporaryDirectory() as tmp:  # the thumbnail only ever lives in memory/queue afterwards
            result = analyse_video(video or data / "videos" / f"{cfg.centre_code}.mp4", cfg.centre_code, layout,
                                   data / "reference" / f"{cfg.centre_code}.png", vcfg, thumb_dir=tmp)
            if cfg.send_thumbnail and result.frame_ref:
                thumb = (Path(tmp) / Path(result.frame_ref).name).read_bytes()
        item = build_item(result, cfg.centre_code, date.today(), captured_at, ingest_id)
    except (VideoError, FileNotFoundError) as exc:
        item = build_offline_item(cfg.centre_code, str(exc), captured_at, ingest_id)
    queue.enqueue(item, thumb)
    transport = transport or HttpTransport(cfg.server_url, cfg.api_key)
    report = Uploader(queue, transport, cfg.batch_size, cfg.send_thumbnail).flush()
    queue.close()
    return item, report


def run_worker(centres: list[str], template: EdgeConfig, interval_min: float, cycles: int | None = None,
               transport: Transport | None = None, sleep: Callable[[float], None] = time.sleep) -> int:
    """Simulated live feed: analyse each centre's clip every `interval_min` minutes, forever (or `cycles` times).

    A failure at one centre is logged and never stops the others. Returns the number of cycles completed.
    """
    done = 0
    while cycles is None or done < cycles:
        for code in centres:
            try:
                item, report = run_once(replace(template, centre_code=code), transport=transport)
                log.info("%s: %s queued, %d sent, %d waiting%s", code, item["kind"], report.sent, report.remaining,
                         f" ({report.error})" if report.error else "")
            except Exception:  # noqa: BLE001 - keep the worker alive
                log.exception("Cycle failed for %s", code)
        done += 1
        if cycles is None or done < cycles:
            sleep(interval_min * 60)
    return done


def main() -> None:
    logging.basicConfig(level="INFO", format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="SkillWatch low-bandwidth edge agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "flush", "status", "worker"):
        s = sub.add_parser(name)
        s.add_argument("--queue", default="data/edge_queue.db")
        if name != "status":
            s.add_argument("--server", default="http://127.0.0.1:8000")
            s.add_argument("--api-key", default=os.getenv("INGEST_API_KEY", ""))
            s.add_argument("--batch-size", type=int, default=10)
            s.add_argument("--no-thumbnail", action="store_true")
        if name in ("run", "worker"):
            s.add_argument("--data-dir", default="data")
            s.add_argument("--profile", default="lowbw", choices=["normal", "lowbw"])
        if name == "run":
            s.add_argument("--centre", required=True)
            s.add_argument("--video")
        if name == "worker":
            s.add_argument("--centres", default="", help="comma-separated codes; default = every centre in data/layouts")
            s.add_argument("--interval-min", type=float, default=5.0)
            s.add_argument("--cycles", type=int, default=None, help="stop after this many rounds (default: run forever)")
    args = p.parse_args()

    if args.cmd == "status":
        q = EdgeQueue(args.queue)
        print(json.dumps(q.stats(), indent=2))
        return
    if args.cmd == "worker":
        codes = [c.strip().upper() for c in args.centres.split(",") if c.strip()] or sorted(
            p.stem for p in (Path(args.data_dir) / "layouts").glob("*.json"))
        if not codes:
            raise SystemExit("No centres found. Run: python -m scripts.generate_demo_footage")
        template = EdgeConfig(codes[0], args.server, args.api_key, args.data_dir, args.queue, args.profile,
                              not args.no_thumbnail, args.batch_size)
        log.info("Worker started for %s every %g min (Ctrl+C to stop)", ", ".join(codes), args.interval_min)
        try:
            run_worker(codes, template, args.interval_min, args.cycles)
        except KeyboardInterrupt:
            log.info("Worker stopped")
        return
    if args.cmd == "run":
        cfg = EdgeConfig(args.centre, args.server, args.api_key, args.data_dir, args.queue, args.profile,
                         not args.no_thumbnail, args.batch_size)
        item, report = run_once(cfg, args.video)
        print(json.dumps({"queued": {k: item[k] for k in ("ingest_id", "kind")}, "flush": report.__dict__}, indent=2))
        return
    q = EdgeQueue(args.queue)  # flush: retry whatever is waiting, regardless of backoff timers
    q.db.execute("UPDATE queue SET next_try_at=0")
    q.db.commit()
    report = Uploader(q, HttpTransport(args.server, args.api_key), args.batch_size, not args.no_thumbnail).flush()
    print(json.dumps(report.__dict__, indent=2))


if __name__ == "__main__":
    main()
