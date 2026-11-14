# Acceptance checklist

Status key: **Verified** = executed and passed (in the build environment, or on the project owner's Windows machine where stated). **Logic verified** = the decision logic ran on real
pipeline output, but the web/database layer was not executed there. **Written, not run** = code and tests exist but have never been
executed, because the build environment could not install FastAPI, MongoDB or PowerShell. Run the commands in the last column to
confirm on your machine. Anything that fails there is a bug to report, not a known limitation.

| # | Item | Status | Evidence | Confirm with |
|---|---|---|---|---|
| 1 | One command starts backend, worker and frontend | Written, not run | `run_all.ps1` starts three windows and opens the browser; read-checked only (no PowerShell in the build environment) | `powershell -ExecutionPolicy Bypass -File .\run_all.ps1` |
| 2 | Login works for all 3 roles with correct permissions | Verified (backend); frontend guard not run | `pytest tests/backend` on the owner's Windows machine: 58 of 59 passed, including login for all roles, role and centre scoping, and JWT security tests. The 1 failure was in the edge-agent test and is fixed (see below) | `python -m scripts.smoke_test`; sign in through the dashboard |
| 3 | Pipeline on demo footage creates records and alerts visible in the dashboard | Verified through the API; dashboard rendering not run | API tests on the owner's machine ran the pipeline, stored observations and alerts, and read them back (overview, centre detail, thumbnail access). Rendering them in React was not executed | `python -m scripts.run_demo --reset`, then open Overview |
| 4 | A deliberately faked attendance sheet is flagged | Verified through the API | SC002 claims 25, camera estimates about 8: `attendance_mismatch`, high severity (API test passed on the owner's machine). `smoke_test` repeats it live with a CSV upload | `python -m scripts.smoke_test` |
| 5 | A removed or missing equipment item is flagged | Verified through the API | SC003 (1 of 2 machines gone) and SC004 (6 of 15 chairs gone) raise `equipment_missing`; SC004's dead machine raises `equipment_not_operable` | Alerts page after a run |
| 6 | Low-bandwidth mode runs and reports its KB/hour figure | Verified (agent, queue, measurement); Written, not run (server ingest) | 17 edge-agent tests pass, including outage then recovery and idempotent retries; the ingest endpoint tests (key checks, idempotency, bad items, camera-offline) passed on the owner's machine. `scripts.bandwidth_report` measured **about 80 KB/hour per centre** (batch of 6, one observation per 5 min); see `docs/BANDWIDTH.md` | `python -m vision.lowbw run --centre SC002 --api-key ...`; the ingest endpoint is covered by 5 API tests |
| 7 | Evaluation script produces the accuracy report | Verified | `python -m scripts.evaluate --n 40` ran on 40 labelled clips under both profiles and wrote `docs/ACCURACY.md` and `docs/ACCURACY.csv` | `python -m scripts.evaluate` (about 3 minutes) |
| 8 | Pytest passes | Mostly verified | 100 test functions. Backend: 58 of 59 passed on the owner's machine (the 1 failure is fixed, not yet re-run there). Vision, edge agent, rules, evaluation and hygiene: 68 test cases pass in the build environment, not yet run on the owner's machine | `pytest -q` |
| 9 | PRIVACY.md and README.md complete and accurate | Written and checked for content | `tests/test_hygiene.py` checks both exist and that PRIVACY.md covers the key points. README commands that use PowerShell were not executed | Read them, then follow the README once on a clean folder |

## Assumptions made

1. Windows 10 with Python 3.10-3.12 and Node.js 20 on the machine; PowerShell 5.1 or newer.
2. MongoDB (local, Docker or Atlas) via `MONGO_URL`. The data layer was exercised only against an in-memory stand-in, never a real MongoDB server; run it with `SKILLWATCH_TEST_MONGO_URL` set to check against yours.
3. The demo footage is synthetic, so the default person counter is the motion-based one. YOLOv8n is implemented behind `VISION_PERSON_DETECTOR=yolo` and unit-tested with a stub, but it was not run or evaluated.
4. YOLO and PyTorch are an optional install (`requirements-yolo.txt`) so the demo installs quickly.
5. COCO has no workbench or machine classes, so equipment uses a zone check against an empty-room reference image, labelled *apparent presence*; operability is the machine's indicator lamp, labelled *apparent operability*.
6. Thumbnails are pixelated at the edge; the server trusts the edge for that.
7. Playwright was not added (needs browser downloads that could not be verified); `scripts/smoke_test.py` and the API tests cover the same flows.
8. The map view was cut, as the brief allows.
9. Email addresses are format-checked only, because the strict validator rejects the `.local` domain used by the demo accounts.

## Known gaps

No map view. No screen for creating centres or editing inventory (use `/docs`). Zone layouts for real cameras are written by hand. Pipeline jobs run in-process. Thumbnails are not deleted automatically. All accuracy figures come from synthetic footage.

## Defect found by the first real test run

`test_edge_agent_end_to_end_flags_faked_attendance` failed on the owner's machine with an extra `equipment_missing` alert for SC002.
Cause: on a 16-second clip the low-bandwidth profile (one frame every 4 s) analysed only 4 frames, too few for a stable background,
so one chair was misread as missing. Fix: the sampler now guarantees at least 8 frames on short clips (`min_frames`), the pipeline notes
when fewer are available, and a regression test covers the case. The accuracy report was regenerated: low-bandwidth headcount error fell
from 1.30 to 1.15 people and its false `equipment_missing` alerts from 3 to 1.
