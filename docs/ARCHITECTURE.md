# Architecture

```
   Centre (edge)                                   Server
 ┌──────────────────────┐   counts + 1 pixelated   ┌──────────────────────────────────────────┐
 │ camera / clip        │   thumbnail (JSON, HTTPS) │ FastAPI                                  │
 │  vision/pipeline.py  │ ────────────────────────▶ │  /api/ingest/batch  (X-Ingest-Key)       │
 │  vision/lowbw.py     │   retry with backoff      │  services/alerts.py  comparison + rules  │
 │  SQLite outbox queue │ ◀──── ack per item ────── │  pymongo ─▶ MongoDB                      │
 └──────────────────────┘                           │  /api/...  JWT + role checks             │
                                                    └───────────────▲──────────────────────────┘
   Same pipeline, run on the server                                   │ axios
   (API-triggered job, demo footage)                  React dashboard (Vite, Tailwind, Recharts)
   POST /api/pipeline/run ───────────────────────────▶  overview · centres · alerts · reports
```

## Folders

| Folder | Role |
|---|---|
| `backend/app/` | FastAPI app: `api/` (routers), `models/` (dataclasses stored in MongoDB), `db/store.py` (data layer), `schemas/` (Pydantic), `services/` (logic), `core/` (settings, JWT) |
| `vision/` | Video analytics: sampling, person counting, equipment zones, privacy, thumbnails, edge agent |
| `frontend/` | React dashboard |
| `scripts/` | `seed`, `generate_demo_footage`, `run_demo`, `evaluate`, `bandwidth_report`, shared `scenario` |
| `data/` | Demo clips, equipment layouts, empty-room references, thumbnails, ground truth |
| `docs/` | This file, API, privacy, accuracy, bandwidth |
| `tests/` | Pytest for backend and vision |

## Request flow for one observation

1. **Sample** frames every N seconds, downscale (`vision/sampler.py`).
2. **Count people** per frame (motion blobs for the demo, YOLOv8n for real footage); rolling median over 5 frames; session estimate = median.
3. **Check equipment** per slot against an empty-room reference, excluding pixels covered by people (*apparent presence*); read indicator lamps on machines (*apparent operability*).
4. **Thumbnail:** pixelate people, draw annotations, downscale, JPEG.
5. **Compare** (`services/comparison.py`, pure functions): estimated vs claimed within `max(2, 15% of claimed)`; detected vs sanctioned inventory.
6. **Rules** raise `attendance_mismatch`, `equipment_missing`, `equipment_not_operable`, `low_quality`; unreadable feeds raise `camera_offline`. One unresolved alert per centre and type is refreshed, not duplicated.
7. **Officers** acknowledge or resolve alerts with comments; nothing is auto-resolved.

## Key design choices

- **Pure core.** Comparison, rules, compliance score and CSV parsing have no database or framework imports, so they are tested directly and easy to explain to an auditor.
- **Edge-first for low bandwidth.** Analysis happens at the centre; only a few hundred bytes of counts and one tiny thumbnail cross the network, queued and retried so outages lose nothing. Idempotent `ingest_id`s make retries safe.
- **Explainable proxies, labelled honestly.** Equipment findings say *apparent*, never *verified*.
- **MongoDB, basic operations only.** `db/store.py` uses only insert, find, replace, `$set`, `$push`, `$inc`, delete, count and indexes, so the same code runs on a real server and on the in-memory stand-in used by the tests. Ids are integers from per-collection counters; dates are stored as ISO strings and enums as their string values. Inventory and alert comments are embedded documents; batches, claims and observations are separate collections. There are no multi-document transactions.
- **Roles enforced on the server.** The frontend hides what a role cannot do, but every endpoint checks the role and the centre.

## Roles

| Role | Can do |
|---|---|
| Super Administrator | Everything: users, centres, inventory, pipeline, alerts |
| Monitoring Officer | Read all centres; run the pipeline; acknowledge, resolve and comment on alerts |
| Training Centre Administrator | See only their own centre; submit attendance (form or CSV); manage their batches; read their alerts |

## Known gaps

- No map view (optional in the brief, cut first).
- No screen for creating centres or editing inventory (use the API docs page).
- Pipeline jobs run in-process (fine for one machine; a real deployment would use a queue).
- No automatic retention of thumbnails.
- YOLO path is implemented and unit-tested with a stub but not evaluated in this repository.
