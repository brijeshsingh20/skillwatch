# SkillWatch AI

AI-based monitoring of training centres for **attendance** and **infrastructure compliance** (Smart India Hackathon problem 26245).

Camera clips are analysed to estimate **how many people are in the room** (a count, nothing more) and whether the sanctioned
**equipment looks present and powered**. Results are compared with what the centre claimed, and discrepancies appear as alerts
on a dashboard so nobody has to watch raw footage.

* **Privacy by design:** aggregate counts only. No face recognition, no identity, no tracking. Saved thumbnails have every person pixelated. See [docs/PRIVACY.md](docs/PRIVACY.md).
* **Low bandwidth:** analysis runs at the centre; only counts and one tiny thumbnail are uploaded (about 80 KB per hour per centre), queued and retried through outages. See [docs/BANDWIDTH.md](docs/BANDWIDTH.md).
* **Honest about limits:** equipment findings say *apparent*, never *verified*, and the accuracy report lists where the system fails. See [docs/ACCURACY.md](docs/ACCURACY.md).

> The demo uses **synthetic footage** (moving shapes as people, labelled rectangles as equipment). It proves the pipeline works end to end.
> It does **not** prove accuracy on real rooms. Read the accuracy report before trusting any number.

## Quick start (Windows 10, PowerShell)

Install once: **Python 3.10-3.12** (tick "Add python.exe to PATH") and **Node.js 20 LTS**. Then, in the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_all.ps1
```

**Start MongoDB first** (see the MongoDB section below; with Docker: `docker run -d --name skillwatch-mongo -p 27017:27017 -v skillwatch-mongo:/data/db mongo:7`).
The first run creates a virtual environment, installs packages (a few minutes), builds the demo data, and opens three windows
(backend, worker, frontend) plus your browser at **http://localhost:5173**. Press Enter in the first window to stop everything.

| Account | Email | Password |
|---|---|---|
| Super Administrator | `superadmin@skillwatch.local` | `Demo@12345` |
| Monitoring Officer | `officer@skillwatch.local` | `Demo@12345` |
| Training Centre Administrator (Pune) | `admin.sc001@skillwatch.local` | `Demo@12345` |

Options: `-ResetDemo` (wipe and rebuild the demo data), `-SkipInstall`, `-NoWorker`, `-WithYolo`, `-WorkerMinutes 5`.
These accounts and the secret in `.env.example` are for the demo only. Change them before any real use.

### The same thing step by step

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m scripts.run_demo --reset        # footage, MongoDB data, seed users, first analysis, 7 days of history (MongoDB must be running)
uvicorn backend.app.main:app --port 8000  # window 1: API, docs at http://127.0.0.1:8000/docs
python -m vision.lowbw worker --api-key dev-ingest-key-change-me   # window 2 (optional): simulated live camera feed
cd frontend; npm install; npm run dev     # window 3: dashboard at http://localhost:5173
```

## The demo world

| Centre | Claimed | Actually in the room | Planted problem |
|---|---|---|---|
| SC001 Pune | 12 | 12 | none (honest baseline) |
| SC002 Nashik | 25 | 8 | faked attendance sheet |
| SC003 Nagpur | 10 | 10 | 1 of 2 machines missing |
| SC004 Aurangabad | 15 | 9 | inflated count, 6 chairs missing, 1 machine not powered, poor camera |

Sign in as the officer, open **Overview**, and click **Run analysis on all centres** (tick *Low-bandwidth mode* to use the cheap profile).

## Checking the acceptance list

With the app running, this one command checks the whole list against the live server and prints PASS or FAIL for each item:

```powershell
python -m scripts.smoke_test
```

It covers: logins for all three roles and their permissions, the pipeline creating records and alerts, a deliberately faked
attendance CSV being flagged (then restored), missing and not-operable equipment being flagged, the low-bandwidth agent surviving a
simulated outage, and the accuracy and privacy documents being served. Automated tests: `pytest -q`.

## Tests

```powershell
pytest -q
```

Backend and vision are covered (auth and roles, comparison and alert rules, CSV parsing, API permissions, the edge agent's queue and
retry logic, the pipeline against ground truth, the evaluation helpers, and project hygiene such as pinned versions and no
placeholder code). **There is no Playwright suite:** it needs browser downloads and could not be verified in the build
environment, so an unverified suite would be worse than none. `scripts.smoke_test` and the API tests cover the same flows.

## Low-bandwidth mode

* **Profile:** `normal` (640 px, a frame every 2 s) or `lowbw` (320 px, every 4 s, stronger JPEG compression). Choose it with the dashboard checkbox, `--profile`, or `VISION_*` environment variables (see `vision/config.py`).
* **Edge agent:** analyses locally, queues the result in SQLite, uploads in batches, retries with exponential backoff, and never double-counts (every item has a unique id).

```powershell
python -m vision.lowbw run --centre SC002 --api-key dev-ingest-key-change-me   # analyse + upload
python -m vision.lowbw status                                                 # what is waiting
python -m vision.lowbw flush --api-key dev-ingest-key-change-me               # retry the queue now
python -m scripts.bandwidth_report                                            # re-measure KB per hour
```

## Accuracy evaluation

```powershell
python -m scripts.evaluate --n 40      # about 3 minutes; rewrites docs/ACCURACY.md and docs/ACCURACY.csv
```

Runs the real pipeline on 40 randomised labelled clips under both profiles and reports headcount error, precision, recall,
false positives and negatives per alert type, and a confusion table. The dashboard's **Accuracy report** page shows it.

## Using real footage

1. Install the YOLO extra (large, pulls in PyTorch): `pip install -r requirements-yolo.txt`, then `$env:VISION_PERSON_DETECTOR = "yolo"` (weights download on first run).
2. For each centre, add `data/layouts/<CODE>.json` (equipment zones: `{"frame_size":[w,h],"slots":[{"id","item_type","box":[x,y,w,h]}]}`; machines may add `"indicator":[x,y,w,h]` over the power lamp) and `data/reference/<CODE>.png` (a photo of the **empty** room from the same fixed camera).
3. Put the clip at `data/videos/<CODE>.mp4` and create the centre in the dashboard API (`POST /api/centres`) with the same code.

There is no tool for drawing zones yet; the layout file is written by hand. The motion counter (default) cannot see people who stand
still, so use YOLO for real rooms. YOLO is implemented but was not evaluated in this repository.

### Upload your own footage (website)

Sign in as the super admin or monitoring officer, open **Analyse footage**, and:

1. choose the centre, a CCTV clip (MP4, MOV, AVI, MKV or WebM, up to 300 MB) and a photo of the same workplace with nobody in it (JPG or PNG, up to 15 MB; a frame from the same camera works well);
2. optionally drag boxes on the photo around each chair, workbench or machine (types you do not mark are not checked; with no boxes only the head-count is analysed);
3. press **Upload and analyse**. The result appears on the page and is saved as a normal observation, so the centre dashboard, alerts and compliance score update. The clip's attendance is compared with the claim for the chosen date.

The photo and the clip must be the same camera view (same width-to-height shape, within 8%). The uploaded video and photo are deleted once the analysis finishes; only a blurred sample frame and the counts are kept. API: `POST /api/pipeline/upload` (multipart: `centre_id`, `video`, `reference`, `zones`, optional `session_date`, `profile`); poll `GET /api/pipeline/jobs/{id}`. Size limits: `MAX_UPLOAD_VIDEO_MB`, `MAX_UPLOAD_IMAGE_MB` in `.env`.

### Worked example: real footage (SC005)

`data/videos/SC005.mp4` is a real 10-second fixed-camera clip of an electronics lab with three people, six chairs and three machines;
`data/real_footage_source/SC005_empty_room.mp4` is the same view with nobody in it, and `data/reference/SC005.png` is the median of its frames.
`data/layouts/SC005.json` sets two options that the synthetic centres do not use:

* `"person_detector": "reference"` counts people as foreground against the empty-room photo, so seated people are counted (the motion counter cannot).
* `"reference_has_equipment": true` says the reference photo already shows the chairs and machines, so an item is present when its zone still **matches** the photo.

```powershell
python -m vision.pipeline --centre SC005      # prints people, chairs, machines
python -m scripts.add_real_centre             # add SC005 to the database (then run analysis from the dashboard)
```

Result on this clip: 3 people, 6 chairs, 3 machines, no "not operable" findings (no indicator lamps are defined for these machines).
Limits: one short clip, so this shows the path works and says nothing about accuracy; zones were drawn by hand for this camera;
people who stand close together merge into one blob (under-count); a person standing entirely inside a chair's zone could be mistaken
for a removed chair; and a machine that is removed or switched off is only detectable if it changes how its zone looks. `scripts.add_real_centre`
has not been run (no FastAPI in the build environment). The pipeline and its tests (`tests/vision/test_real_footage.py`) were run.

## MongoDB

All application data (users, centres with their sanctioned inventory, batches, attendance claims, observations, alerts with their comments) is stored in MongoDB. Start one of these before the backend:

* **Docker (simplest):** `docker run -d --name skillwatch-mongo -p 27017:27017 -v skillwatch-mongo:/data/db mongo:7` (start it again later with `docker start skillwatch-mongo`).
* **Windows installer:** MongoDB Community Server from mongodb.com; install it as a service, which listens on `mongodb://localhost:27017`.
* **Atlas (cloud, free tier):** create a cluster, allow your IP, and put its connection string in `MONGO_URL`.

Set `MONGO_URL` and `MONGO_DB` in `.env` (defaults: `mongodb://localhost:27017` and `skillwatch`). Indexes are created on first start. Ids are small integers (a counter per collection), so URLs and logins work as before.

Things to know: there are no multi-document transactions (they need a replica set), so a crash in the middle of an operation that writes several documents can leave partial data. Deleting a centre removes its batches, claims, observations and alerts, with the centre itself deleted last so a failed delete can simply be repeated. The edge agent keeps its own small SQLite queue on each centre's computer; that is separate from the server database.

The tests run without MongoDB by default (an in-memory stand-in, `tests/fake_mongo.py`). To run them against a real server: `$env:SKILLWATCH_TEST_MONGO_URL="mongodb://localhost:27017"; pytest -q` (each test uses a throw-away database that is dropped afterwards).

## Managing centres from the dashboard (no Swagger needed)

Signed in as a Super Administrator, you can add and change centres with ordinary forms:

- **Centres page > Add centre**: code, name, district, state, capacity, optional location, and how many chairs, workbenches and machines the centre should have.
- **Centre page > Manage centre**: edit the details, change the equipment numbers, add or remove batches (class timings, with day tick-boxes and time pickers), or delete the centre (you must type its code to confirm).

New equipment numbers apply from the next analysis. Removing a batch also deletes its attendance records. Other roles do not see these buttons. The Swagger page at `/docs` still exists for developers.

## Storing thumbnails in the cloud (Cloudinary)

By default every thumbnail is a file in `data/thumbnails/`. That is fine on your own PC, but most free hosts (Render, Railway, Fly and similar) wipe their disk on each restart or redeploy, which would delete every image the dashboard shows. For a deployment, send thumbnails to Cloudinary instead:

1. Create a free Cloudinary account and copy the cloud name, API key and API secret from the dashboard.
2. Set these in `.env` (or in the host's environment-variable page):
   `STORAGE_BACKEND=cloudinary`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`.
3. Run `pip install -r requirements.txt` again (it now includes the `cloudinary` package) and restart the backend. A wrong or missing setting stops the server at start-up with a clear message.

What changes: after an analysis, the pixelated thumbnail is uploaded with delivery type `authenticated` (its URL needs a signature, so it cannot be opened by guessing a link), the local copy is deleted, and the database stores `cloud:skillwatch/thumbnails/<name>`. The dashboard code is unchanged: it still asks `GET /api/observations/{id}/frame`, which checks the login and the centre and then fetches the image from Cloudinary for the user. Deleting a centre also deletes its thumbnails from Cloudinary. If an upload fails, the observation is still saved with the local file and the error is logged. Existing observations that point at local files keep working.

### Also keeping the uploaded video and photo (optional)

By default the uploaded CCTV clip and the empty-room photo are **not** sent to the cloud: they are deleted after analysis, which is what `docs/PRIVACY.md` promises. To keep them in Cloudinary as well, add `STORE_UPLOADS_IN_CLOUD=true` (it needs `STORAGE_BACKEND=cloudinary`).

- After the analysis, the video (sent in 6 MB chunks) and the photo are uploaded as `authenticated` assets under `skillwatch/uploads/`, and their references are saved on the observation as `video_ref` and `reference_ref`. The local temporary copies are still deleted.
- On the Upload page, the result card gets a "Show stored video and photo" button. It calls `GET /api/observations/{id}/media`, which only super admins and monitoring officers may use (centre admins cannot), and returns signed links.
- If the cloud upload fails, the analysis is still saved and the result shows a note.
- Deleting a centre also deletes its stored videos and photos.
- Check your Cloudinary plan's maximum video file size: `MAX_UPLOAD_VIDEO_MB` allows 300 MB by default, which may be more than a free plan accepts.
- Read `docs/PRIVACY.md` first. Footage of trainees now sits with a third party until you delete it, so decide a retention period and tell centres.

The synthetic demo clips in `data/videos/` are read-only and ship with the app.

The free Cloudinary plan has monthly storage and bandwidth limits; check the current numbers on their pricing page before relying on it.

## Project layout

```
backend/   FastAPI app (api, models, schemas, services, core)
vision/    sampling, counting, equipment zones, privacy, thumbnails, edge agent (lowbw.py)
frontend/  React + Vite + Tailwind dashboard
scripts/   seed, generate_demo_footage, run_demo, evaluate, bandwidth_report, smoke_test
data/      demo clips, layouts, references, thumbnails, ground truth
docs/      ARCHITECTURE, API, PRIVACY, ACCURACY, BANDWIDTH
tests/     pytest (backend, vision, hygiene)
```

## Troubleshooting

* **"running scripts is disabled"**: use the `-ExecutionPolicy Bypass` command shown above.
* **Port 8000 or 5173 already in use**: close the old windows, or stop the other program.
* **`pip install` fails on `bcrypt` or `psycopg2`**: use Python 3.10-3.12 (newer versions may lack prebuilt packages).
* **Dashboard says "Cannot reach the server"**: the backend window shows the error; make sure it is running on port 8000.
* **Blank pages after a code update**: run `python -m scripts.run_demo --reset` (this wipes the collections and rebuilds the demo data).
* **`ServerSelectionTimeoutError` or "Cannot reach the server"**: MongoDB is not running or `MONGO_URL` is wrong; start it (see the MongoDB section) and restart the backend.
* **Edge agent says "Server refused the API key"**: the key after `--api-key` must equal `INGEST_API_KEY` in `.env`.

## Known limits

No map view, no screen for creating centres or editing inventory (use the API docs page), pipeline jobs run in-process, no
automatic deletion of old thumbnails, and the accuracy numbers come from synthetic data. Details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/ACCURACY.md](docs/ACCURACY.md).
