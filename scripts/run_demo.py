"""One-shot demo: seed data, make footage if missing, run the pipeline, backfill a week of history.

Usage (project root):  python -m scripts.run_demo [--reset] [--no-history] [--profile normal|lowbw]
"""
import argparse
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.db.session import get_store
from backend.app.models import Centre
from backend.app.services.pipeline_runner import run_for_centre
from scripts.generate_demo_footage import generate_centre
from scripts.scenario import SCENARIO
from scripts.seed import HISTORY_DAYS, reset_all, seed
from vision.pipeline import analyse_centre

log = logging.getLogger("demo")


def main() -> None:
    logging.basicConfig(level="INFO", format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--no-history", action="store_true", help="only today's observation")
    parser.add_argument("--profile", default="normal", choices=["normal", "lowbw"])
    args = parser.parse_args()

    data = Path(get_settings().data_dir)
    for sc in SCENARIO:
        if not (data / "videos" / f"{sc['code']}.mp4").exists():
            log.info("Generating footage for %s", sc["code"])
            generate_centre(sc, data)

    db = get_store()
    db.ensure_indexes()
    if args.reset:
        reset_all(db)
    seed(db)
    now = datetime.now(timezone.utc)
    for centre in db.find(Centre, sort=[("id", 1)]):
        result = analyse_centre(centre.code, data, args.profile)
        days = [] if args.no_history else list(range(HISTORY_DAYS, 0, -1))
        for back in days:  # oldest first, so today's observation is the latest
            run_for_centre(db, centre, cached_result=result, captured_at=now - timedelta(days=back),
                           session_date=(now - timedelta(days=back)).date())
        out = run_for_centre(db, centre, cached_result=result, captured_at=now)
        log.info("%s: estimated=%s claimed=%s alerts=%s", centre.code, out.get("estimated_count"),
                 out.get("claimed_count"), len(out.get("alert_ids", [])))
    log.info("Demo ready. Start the API: uvicorn backend.app.main:app --reload")


if __name__ == "__main__":
    main()
