"""Register the real-footage centre SC005 (clip + empty-room reference + zone layout already in data/).

Usage (from project root, after the demo database exists):  python -m scripts.add_real_centre [--claimed 3]
Idempotent: does nothing if SC005 already exists. Edit the constants to describe a different centre.
"""
import argparse
import logging
from datetime import date, time

from backend.app.core.security import hash_password
from backend.app.db.session import get_store
from backend.app.models import AttendanceClaim, Batch, Centre, ClaimSource, InventoryItem, ItemType, Role, User

log = logging.getLogger("add_real_centre")
CODE = "SC005"
SANCTIONED = {"chair": 6, "machine": 3}  # what the layout file's slots list: 6 chairs, 3 machines


def main() -> None:
    logging.basicConfig(level="INFO", format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--claimed", type=int, default=3, help="attendance the centre claims for today (default 3 = honest)")
    args = ap.parse_args()
    db = get_store()
    db.ensure_indexes()
    if db.one(Centre, {"code": CODE}):
        log.info("%s already exists; nothing to do", CODE)
        return
    centre = Centre(code=CODE, name="Electronics and Robotics Lab (real footage)", district="Pune",
                    state="Maharashtra", latitude=18.5204, longitude=73.8567, approved_capacity=10,
                    inventory=[InventoryItem(ItemType(item), qty) for item, qty in SANCTIONED.items()])
    db.add(centre)
    batch = db.add(Batch(centre_id=centre.id, name="Morning Batch", start_time=time(9, 0), end_time=time(13, 0),
                         enrolled=args.claimed))
    db.add(AttendanceClaim(centre_id=centre.id, batch_id=batch.id, session_date=date.today(),
                           claimed_count=args.claimed, source=ClaimSource.SEED))
    email = f"admin.{CODE.lower()}@skillwatch.local"
    if db.one(User, {"email": email}) is None:
        db.add(User(email=email, full_name="Real Footage Centre Administrator",
                    hashed_password=hash_password("Demo@12345"), role=Role.CENTRE_ADMIN, centre_id=centre.id))
    log.info("Created %s. Now run the pipeline from the dashboard or: python -m vision.pipeline --centre %s", CODE, CODE)


if __name__ == "__main__":
    main()
