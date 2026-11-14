"""End-to-end check of the acceptance checklist against a RUNNING server (after run_all.ps1 / run_demo).

Usage:  python -m scripts.smoke_test [--base http://127.0.0.1:8000]
Uses only the standard library plus this repo's edge agent. Prints PASS/FAIL per item and exits 1 on any failure.
It briefly changes SC001's attendance to a fake figure to prove the flag works, then restores it.
"""
import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date
from pathlib import Path

PASSWORD = "Demo@12345"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)


def call(base: str, method: str, path: str, token: str | None = None, body=None, form=None, raw=False, files=None):
    headers, data = {}, None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif files is not None:
        boundary = uuid.uuid4().hex
        parts = []
        for key, value in files["fields"].items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{files["name"]}"\r\n'
                      f"Content-Type: text/csv\r\n\r\n").encode() + files["content"] + f"\r\n--{boundary}--\r\n".encode())
        data = b"".join(parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = resp.read()
            return resp.status, (payload if raw else json.loads(payload or b"null"))
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload)
        except ValueError:
            return exc.code, payload


def login(base: str, email: str) -> str | None:
    status, data = call(base, "POST", "/api/auth/login", form={"username": email, "password": PASSWORD})
    return data["access_token"] if status == 200 else None


def read_env_key() -> str:
    env = Path(".env")
    if os.getenv("INGEST_API_KEY"):
        return os.environ["INGEST_API_KEY"]
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("INGEST_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def unresolved_by_centre(base: str, token: str) -> dict[str, set[str]]:
    _, alerts = call(base, "GET", "/api/alerts", token)
    out: dict[str, set[str]] = {}
    for a in alerts:
        if a["status"] != "resolved":
            out.setdefault(a["centre_code"], set()).add(a["alert_type"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    base = parser.parse_args().base.rstrip("/")

    status, _ = call(base, "GET", "/api/health")
    check("Backend is reachable", status == 200, base)
    if status != 200:
        return 1

    # Roles and permissions
    tokens = {r: login(base, e) for r, e in (("super", "superadmin@skillwatch.local"), ("officer", "officer@skillwatch.local"),
                                              ("centre", "admin.sc001@skillwatch.local"))}
    check("Login works for all 3 roles", all(tokens.values()))
    if not all(tokens.values()):
        return 1
    roles = {r: call(base, "GET", "/api/auth/me", t)[1]["role"] for r, t in tokens.items()}
    check("Roles resolve correctly", roles == {"super": "super_admin", "officer": "monitoring_officer", "centre": "centre_admin"}, str(roles))
    check("Wrong password is refused", call(base, "POST", "/api/auth/login", form={"username": "officer@skillwatch.local", "password": "x"})[0] == 401)
    _, centres = call(base, "GET", "/api/centres", tokens["super"])
    ids = {c["code"]: c["id"] for c in centres}
    check("Centre admin cannot open another centre", call(base, "GET", f"/api/centres/{ids['SC002']}", tokens["centre"])[0] == 403)
    check("Centre admin cannot run the pipeline", call(base, "POST", "/api/pipeline/run", tokens["centre"], body={})[0] == 403)
    check("Officer cannot manage users", call(base, "GET", "/api/users", tokens["officer"])[0] == 403)
    check("Super admin can manage users", call(base, "GET", "/api/users", tokens["super"])[0] == 200)

    # Pipeline -> records -> alerts
    status, job = call(base, "POST", "/api/pipeline/run?wait=true", tokens["officer"], body={})
    check("Pipeline run on demo footage completes", status == 200 and job["status"] == "done", job.get("error") or "")
    by_centre = unresolved_by_centre(base, tokens["officer"])
    check("Honest centre (SC001) has no alerts", "SC001" not in by_centre, str(by_centre.get("SC001", "")))
    check("Faked attendance flagged (SC002)", "attendance_mismatch" in by_centre.get("SC002", set()))
    check("Missing equipment flagged (SC003)", "equipment_missing" in by_centre.get("SC003", set()))
    check("Not-operable equipment and low quality flagged (SC004)",
          {"equipment_not_operable", "low_quality", "attendance_mismatch", "equipment_missing"} <= by_centre.get("SC004", set()))
    _, detail = call(base, "GET", f"/api/centres/{ids['SC002']}/detail", tokens["super"])
    obs = detail["latest_observation"]
    check("Dashboard data has records and a compliance score", obs is not None and detail["compliance_score"] is not None)
    status, img = call(base, "GET", f"/api/observations/{obs['id']}/frame", tokens["super"], raw=True)
    check("Annotated thumbnail is served", status == 200 and img[:3] == b"\xff\xd8\xff", f"{len(img) / 1024:.1f} KB" if status == 200 else "")

    # A deliberately faked attendance sheet (CSV) is flagged, then restored
    _, centre = call(base, "GET", f"/api/centres/{ids['SC001']}", tokens["centre"])
    today = date.today().isoformat()
    fake = f"session_date,claimed_count\n{today},30\n".encode()
    status, res = call(base, "POST", "/api/attendance/csv", tokens["centre"], files={"fields": {"centre_id": ids["SC001"]}, "name": "fake.csv", "content": fake})
    check("Faked CSV attendance is accepted by the form", status == 200 and not res["errors"])
    call(base, "POST", "/api/pipeline/run?wait=true", tokens["officer"], body={"centre_id": ids["SC001"]})
    flagged = "attendance_mismatch" in unresolved_by_centre(base, tokens["officer"]).get("SC001", set())
    check("Faked CSV attendance gets flagged (SC001: claimed 30)", flagged)
    honest = f"session_date,claimed_count\n{today},12\n".encode()
    call(base, "POST", "/api/attendance/csv", tokens["centre"], files={"fields": {"centre_id": ids["SC001"]}, "name": "ok.csv", "content": honest})
    _, alerts = call(base, "GET", f"/api/alerts?centre_id={ids['SC001']}&status=open", tokens["officer"])
    for a in alerts:
        call(base, "PATCH", f"/api/alerts/{a['id']}/status", tokens["officer"], body={"status": "resolved", "comment": "smoke test restored"})

    # Low-bandwidth mode with an outage
    key = read_env_key()
    check("INGEST_API_KEY is configured", bool(key))
    if key:
        from vision.lowbw import EdgeConfig, EdgeQueue, HttpTransport, Uploader, run_once

        with tempfile.TemporaryDirectory() as tmp:
            qpath = str(Path(tmp) / "q.db")
            down = EdgeConfig("SC002", server_url="http://127.0.0.1:9", api_key=key, queue_path=qpath)
            _, rep = run_once(down)
            check("Outage: item is kept in the offline queue", rep.remaining == 1 and rep.error is not None)
            q = EdgeQueue(qpath)
            q.db.execute("UPDATE queue SET next_try_at=0")
            q.db.commit()
            rep2 = Uploader(q, HttpTransport(base, key)).flush()
            check("Recovery: queued item uploaded after the link returns", rep2.sent == 1 and rep2.remaining == 0)
            _, rep3 = run_once(EdgeConfig("SC002", server_url=base, api_key=key, queue_path=qpath))
            kb = rep3.bytes_sent / 1024
            check("Low-bandwidth upload is tiny (counts + 1 thumbnail)", rep3.sent == 1 and rep3.bytes_sent < 15_000, f"{kb:.1f} KB for one observation")
            print(f"      Measured request body: {kb:.1f} KB for one observation (about {kb * 12:.0f} KB/hour at one every 5 min, "
                  f"before headers; batched figures are in docs/BANDWIDTH.md)")

    # Documents
    status, acc = call(base, "GET", "/api/reports/accuracy", tokens["officer"])
    check("Accuracy report is available", status == 200 and "Headcount" in acc.get("markdown", ""))
    status, priv = call(base, "GET", "/api/reports/privacy", tokens["officer"])
    check("Privacy note is available", status == 200 and "face recognition" in priv.get("markdown", "").lower())

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
