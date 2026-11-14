# API reference

Base URL `http://127.0.0.1:8000`. Interactive docs with try-it-out: `/docs` (Swagger) and `/redoc`.
All endpoints except `/api/health`, `/api/auth/login` and `/api/ingest/*` need `Authorization: Bearer <token>`.
Errors are JSON `{"detail": "..."}` with 401 (not signed in), 403 (role or centre not allowed), 404, 409 (conflict), 422 (invalid input).

Roles: **SA** Super Administrator, **MO** Monitoring Officer, **CA** Training Centre Administrator (own centre only).

## Auth and users
| Method and path | Who | Notes |
|---|---|---|
| `POST /api/auth/login` | public | Form fields `username` (email) and `password`. Returns `{access_token, token_type, user}`. |
| `GET /api/auth/me` | any | The signed-in user. |
| `GET /api/users` | SA | |
| `POST /api/users` | SA | `{email, full_name, password (min 8), role, centre_id}`. `centre_id` required for `centre_admin`. 409 if the email exists. |
| `PATCH /api/users/{id}` | SA | Any of `full_name, password, role, centre_id, is_active`. |
| `DELETE /api/users/{id}` | SA | Soft delete (deactivates). |

## Centres
| Method and path | Who | Notes |
|---|---|---|
| `GET /api/centres` | any | Summaries with `compliance_score`, `open_alerts` (unresolved), `last_observed_at`. CA sees only their own. |
| `POST /api/centres` | SA | `{code, name, district, state, latitude?, longitude?, approved_capacity, inventory[], batches[]}`. Code is upper-cased; 409 if it exists. |
| `GET /api/centres/{id}` | any (CA: own) | Full record with inventory and batches. |
| `PATCH /api/centres/{id}` | SA | Name, location, capacity. |
| `DELETE /api/centres/{id}` | SA | Removes the centre and its data; its users are detached. |
| `PUT /api/centres/{id}/inventory` | SA | Replaces the sanctioned inventory: `[{item_type: chair/workbench/machine, quantity}]`, one line per type. |
| `POST /api/centres/{id}/batches` | SA, CA (own) | `{name, start_time, end_time, days, enrolled}`. |
| `DELETE /api/centres/{id}/batches/{batch_id}` | SA, CA (own) | |
| `GET /api/centres/{id}/observations?limit=50` | any (CA: own) | Newest first. |
| `GET /api/centres/{id}/detail` | any (CA: own) | Compliance score, latest observation, inventory table, 14-day claimed-vs-estimated timeline, unresolved alerts. |

## Attendance
| Method and path | Who | Notes |
|---|---|---|
| `POST /api/attendance` | SA, CA (own) | `{centre_id, batch_id, session_date, claimed_count}`. One claim per batch and date; resubmitting updates it. |
| `POST /api/attendance/csv` | SA, CA (own) | Multipart: `centre_id`, `file`. Columns `session_date` (YYYY-MM-DD), `claimed_count`, `batch` (id or name; optional if the centre has one batch). Max 1 MB / 1000 rows. Returns `{created, updated, errors:[{row, error}]}`; bad rows are skipped, good rows are saved. |
| `GET /api/attendance?centre_id=&limit=` | any (CA: own) | |

## Vision pipeline
| Method and path | Who | Notes |
|---|---|---|
| `POST /api/pipeline/run?wait=false` | SA, MO | Body `{centre_id?, profile: "normal" or "lowbw", session_date?}`. No `centre_id` = all centres. Returns 202 and a job; `wait=true` runs inline and returns 200. Reads `data/videos/<CODE>.mp4`. |
| `GET /api/pipeline/jobs/{job_id}` | SA, MO | `status`: queued, running, done, failed; `results[]` per centre. |

A centre whose video cannot be read gets a `camera_offline` alert instead of crashing the job.

## Alerts and observations
| Method and path | Who | Notes |
|---|---|---|
| `GET /api/alerts?status=&severity=&alert_type=&centre_id=&limit=` | any (CA: own) | Newest first. |
| `GET /api/alerts/{id}` | any (CA: own) | Includes officer comments. |
| `PATCH /api/alerts/{id}/status` | SA, MO | `{status: open/acknowledged/resolved, comment?}`. Allowed: open to acknowledged or resolved; acknowledged to resolved or open; resolved to open (reopen). Otherwise 409. |
| `POST /api/alerts/{id}/comments` | SA, MO | `{text}`. |
| `GET /api/observations/{id}/frame` | any (CA: own centre) | The pixelated annotated JPEG. |
| `GET /api/observations/{id}/media` | SA, MO | Signed links `{video_url, photo_url}` to the uploaded clip and empty-room photo. 404 unless `STORE_UPLOADS_IN_CLOUD=true` kept them. |

Alert types: `attendance_mismatch`, `equipment_missing`, `equipment_not_operable`, `camera_offline`, `low_quality`. Severities: `low`, `medium`, `high`.
There is at most one unresolved alert per centre and type; a new finding refreshes it.

## Dashboard and documents
| Method and path | Who | Notes |
|---|---|---|
| `GET /api/dashboard/overview` | any (CA: own) | KPIs: centres, unresolved alerts by severity and type, average compliance, observations, cameras not online. |
| `GET /api/reports/accuracy` | any | `{name, markdown}` from `docs/ACCURACY.md` (404 until generated). |
| `GET /api/reports/privacy` | any | From `docs/PRIVACY.md`. |
| `GET /api/health` | public | `{"status": "ok"}` |

## Low-bandwidth edge ingest
`POST /api/ingest/batch` with header `X-Ingest-Key: <INGEST_API_KEY>` (503 if the key is not configured, 401 if wrong). Up to 50 items.

```json
{"observations": [
  {"ingest_id": "3f2a9c1e5b7d4e8f", "kind": "observation", "centre_code": "SC002",
   "captured_at": "2026-11-11T09:00:00+00:00", "session_date": "2026-11-11",
   "estimated_count": 8, "items_detected": {"chair": 25, "workbench": 5, "machine": 2},
   "items_not_operable": {}, "confidence": 0.93, "frame_quality": 1.0, "low_quality": false,
   "thumbnail_b64": "<JPEG up to 60 KB, base64>"},
  {"ingest_id": "a81c0d77e2b34f10", "kind": "camera_offline", "centre_code": "SC003",
   "captured_at": "2026-11-11T09:05:00+00:00", "reason": "stream timeout"}
]}
```
Response: `{"results": [{"ingest_id", "status": "created|duplicate|rejected", "observation_id", "alerts", "error"}]}`.
Re-sending an `ingest_id` returns `duplicate` (safe retries). Items are processed independently; one rejected item does not affect the others. Item-level problems (unknown centre, bad thumbnail) are `rejected`; schema problems return 422 for the whole batch (the edge agent then retries items one by one).

## Example (PowerShell)
```powershell
$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/auth/login `
     -Body @{username="officer@skillwatch.local"; password="Demo@12345"}
$h = @{Authorization = "Bearer $($r.access_token)"}
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/alerts?status=open -Headers $h
```
