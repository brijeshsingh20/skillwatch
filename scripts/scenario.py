"""Single source of truth for the demo world.

The seed script uses `claimed_count` and `sanctioned`; the footage generator (Stage 3)
uses `true_count`, `present` and `not_operable` to draw the scene; the evaluation script
uses `expected_alerts` as ground truth for flags.
"""
from typing import TypedDict


class CentreScenario(TypedDict):
    code: str
    name: str
    district: str
    state: str
    latitude: float
    longitude: float
    capacity: int
    camera_profile: str  # "good" | "poor"
    sanctioned: dict[str, int]
    present: dict[str, int]
    not_operable: dict[str, int]
    true_count: int
    claimed_count: int
    expected_alerts: list[str]


SCENARIO: list[CentreScenario] = [
    {   # Honest centre: everything matches.
        "code": "SC001", "name": "Pune Skill Hub", "district": "Pune", "state": "Maharashtra",
        "latitude": 18.5204, "longitude": 73.8567, "capacity": 30, "camera_profile": "good",
        "sanctioned": {"chair": 12, "workbench": 4, "machine": 2},
        "present": {"chair": 12, "workbench": 4, "machine": 2},
        "not_operable": {},
        "true_count": 12, "claimed_count": 12, "expected_alerts": [],
    },
    {   # Inflated attendance sheet (25 claimed, 8 in the room).
        "code": "SC002", "name": "Nashik Rural Training Centre", "district": "Nashik", "state": "Maharashtra",
        "latitude": 19.9975, "longitude": 73.7898, "capacity": 40, "camera_profile": "good",
        "sanctioned": {"chair": 25, "workbench": 5, "machine": 2},
        "present": {"chair": 25, "workbench": 5, "machine": 2},
        "not_operable": {},
        "true_count": 8, "claimed_count": 25, "expected_alerts": ["attendance_mismatch"],
    },
    {   # Honest attendance, but one machine is missing.
        "code": "SC003", "name": "Nagpur Fab Lab", "district": "Nagpur", "state": "Maharashtra",
        "latitude": 21.1458, "longitude": 79.0882, "capacity": 25, "camera_profile": "good",
        "sanctioned": {"chair": 10, "workbench": 4, "machine": 2},
        "present": {"chair": 10, "workbench": 4, "machine": 1},
        "not_operable": {},
        "true_count": 10, "claimed_count": 10, "expected_alerts": ["equipment_missing"],
    },
    {   # Everything wrong, on a poor camera: inflated count, missing chairs, a dead machine.
        "code": "SC004", "name": "Aurangabad Skills Park", "district": "Chhatrapati Sambhajinagar", "state": "Maharashtra",
        "latitude": 19.8762, "longitude": 75.3433, "capacity": 35, "camera_profile": "poor",
        "sanctioned": {"chair": 15, "workbench": 6, "machine": 3},
        "present": {"chair": 9, "workbench": 6, "machine": 3},
        "not_operable": {"machine": 1},
        "true_count": 9, "claimed_count": 15,
        "expected_alerts": ["attendance_mismatch", "equipment_missing", "equipment_not_operable", "low_quality"],
    },
]
