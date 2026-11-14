"""Seed users, centres, inventory, batches and attendance claims.

Usage (from project root):  python -m scripts.seed [--reset]
"""
import argparse
import logging
import random
from datetime import date, time, timedelta

from backend.app.core.security import hash_password
from backend.app.db.session import get_store
from backend.app.db.store import Store
from backend.app.models import (
    AttendanceClaim, Batch, CameraStatus, Centre, ClaimSource, InventoryItem, ItemType, Role, User,
)
from scripts.scenario import SCENARIO

log = logging.getLogger("seed")
DEMO_PASSWORD = "Demo@12345"
HISTORY_DAYS = 7


def reset_all(db: Store) -> None:
    db.drop_all_data()


def _add_user(db: Store, email: str, name: str, role: Role, centre_id: int | None = None) -> None:
    if db.one(User, {"email": email}) is None:
        db.add(User(email=email, full_name=name, hashed_password=hash_password(DEMO_PASSWORD),
                    role=role, centre_id=centre_id))


def seed(db: Store, today: date | None = None, rng_seed: int = 42) -> dict[str, int]:
    """Idempotent: centres that already exist (by code) are left untouched."""
    today = today or date.today()
    rng = random.Random(rng_seed)
    created = 0

    _add_user(db, "superadmin@skillwatch.local", "Demo Super Administrator", Role.SUPER_ADMIN)
    _add_user(db, "officer@skillwatch.local", "Demo Monitoring Officer", Role.MONITORING_OFFICER)

    for sc in SCENARIO:
        if db.one(Centre, {"code": sc["code"]}):
            continue
        centre = Centre(
            code=sc["code"], name=sc["name"], district=sc["district"], state=sc["state"],
            latitude=sc["latitude"], longitude=sc["longitude"], approved_capacity=sc["capacity"],
            camera_status=CameraStatus.LOW_QUALITY if sc["camera_profile"] == "poor" else CameraStatus.ONLINE,
            inventory=[InventoryItem(ItemType(item), qty) for item, qty in sc["sanctioned"].items()],
        )
        db.add(centre)
        created += 1

        batch = Batch(centre_id=centre.id, name="Morning Batch", start_time=time(9, 0), end_time=time(13, 0),
                      enrolled=min(sc["capacity"], sc["claimed_count"] + 3))
        db.add(batch)

        # Past sessions: honest centres claim close to the truth; inflated centres keep inflating.
        inflated = sc["claimed_count"] > sc["true_count"]
        for back in range(HISTORY_DAYS, 0, -1):
            base = sc["claimed_count"] if inflated else sc["true_count"]
            jitter = rng.randint(-1, 1)
            db.add(AttendanceClaim(centre_id=centre.id, batch_id=batch.id, session_date=today - timedelta(days=back),
                                   claimed_count=max(0, base + jitter), source=ClaimSource.SEED))
        # Today's claim is exactly the scenario value (what the demo pipeline run is compared against).
        db.add(AttendanceClaim(centre_id=centre.id, batch_id=batch.id, session_date=today,
                               claimed_count=sc["claimed_count"], source=ClaimSource.SEED))

        _add_user(db, f"admin.{sc['code'].lower()}@skillwatch.local", f"{sc['name']} Administrator",
                  Role.CENTRE_ADMIN, centre.id)

    return {"centres_created": created}


def main() -> None:
    logging.basicConfig(level="INFO", format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="wipe all collections first")
    args = parser.parse_args()
    db = get_store()
    db.ensure_indexes()
    if args.reset:
        reset_all(db)
        log.info("All collections cleared")
    result = seed(db)
    log.info("Seed complete: %s", result)
    log.info("Logins (password %s): superadmin@skillwatch.local, officer@skillwatch.local, admin.sc001@skillwatch.local",
             DEMO_PASSWORD)


if __name__ == "__main__":
    main()
