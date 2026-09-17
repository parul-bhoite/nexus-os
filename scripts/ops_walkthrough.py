"""S10.1's acceptance, driven through the running API as a client would.

`doc/15` S10.1:

    a founder creates a project and a task through the app; both tiles render
    from the database; a second member of the workspace sees them and a member
    of another workspace does not.

The suite asserts each half separately and hermetically. This asserts the whole
sentence in order, over HTTP, with cookies and CSRF, against whatever database
the API is actually pointed at — the distinction `CLAUDE.md` draws between code
existing and a phase being complete.

    services/api/.venv/bin/python scripts/ops_walkthrough.py

Expects an API on 127.0.0.1:8001 and the mail sink writing to `.mail`.

**What it does not prove.** It drives the API, not the browser, so the rendering
of the count figure is still `CountFigure.test.tsx`'s job. And it creates one
workspace per run, which is why every figure it asserts is a count rather than a
comparison against anything earlier.
"""

from __future__ import annotations

import email
import email.policy
import pathlib
import re
import sys
import time

import httpx

API = "http://127.0.0.1:8001"
MAIL = pathlib.Path(__file__).resolve().parents[1] / ".mail"
PW = "correct horse battery staple 9"

ok = fail = 0


def check(label: str, cond: object, detail: str = "") -> None:
    global ok, fail
    if cond:
        ok += 1
        print(f"  \033[32mPASS\033[0m {label}")
    else:
        fail += 1
        print(f"  \033[31mFAIL\033[0m {label} — {detail}")


def newest_mail(since: float) -> str:
    """Decode it as mail — the sink writes quoted-printable, so a raw read
    soft-wraps the token at column 76 and every regex over it lies."""
    for _ in range(20):
        files = sorted(MAIL.glob("*.eml"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files and files[0].stat().st_mtime > since:
            msg = email.message_from_bytes(files[0].read_bytes(), policy=email.policy.default)
            parts = [msg] if not msg.is_multipart() else list(msg.walk())
            return "\n".join(
                part.get_content() for part in parts if part.get_content_maintype() == "text"
            )
        time.sleep(0.25)
    return ""


def founder(tag: str) -> httpx.Client:
    """Register, verify, log in and create a company. Returns a live client."""
    stamp = f"{int(time.time())}{tag}"
    mail = f"founder+{stamp}@ops-{stamp}.om"
    client = httpx.Client(base_url=API, timeout=30.0)

    t0 = time.time()
    client.post("/auth/register", json={"email": mail, "password": PW, "full_name": "Ops Walk"})
    body = newest_mail(t0)
    found = re.search(r"token=([A-Za-z0-9_\-\.]{16,})", body)
    if not found:
        sys.exit("no verification token — is the mail sink writing to .mail?")
    client.post("/auth/verify-email", json={"token": found.group(1)})
    client.post("/auth/login", json={"email": mail, "password": PW})

    csrf = {"X-CSRF-Token": client.cookies.get("nexus_csrf") or ""}
    client.post(
        "/companies",
        json={
            "name": f"Ops Trading {stamp}",
            "website_url": f"https://ops-{stamp}.om",
            "country": "OM",
            "reporting_currency": "OMR",
            "headcount_band": "11-50",
        },
        headers=csrf,
    )
    return client


def token(client: httpx.Client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nexus_csrf") or ""}


print("\n\033[1m1. A founder, and a workspace that has recorded nothing\033[0m")
a = founder("a")
r = a.get("/ops")
check("GET /ops -> 200", r.status_code == 200, r.text[:200])
check("nothing recorded yet", r.json()["projects"] == [] and r.json()["tasks"] == [], r.text[:200])
check(
    "and it says so with an empty stamp, not a date",
    r.json()["recorded_at"] == "",
    r.text[:200],
)

r = a.get("/dashboards/surface")
before = [b["key"] for b in r.json().get("measured", [])]
check(
    "no ops tile carries a figure before anything is recorded",
    not any(k.startswith("operations.") for k in before),
    str(before),
)

print("\n\033[1m2. Record a project and a task\033[0m")
r = a.post(
    "/ops/projects",
    json={"name": "Muscat fit-out", "status": "active", "client": "Al Bahja", "due_on": "2026-01-05"},
    headers=token(a),
)
check("POST /ops/projects -> 201", r.status_code == 201, r.text[:300])
project_id = r.json().get("id") if r.status_code == 201 else None

r = a.post(
    "/ops/tasks",
    json={"title": "Order the glazing", "status": "todo", "project_id": project_id, "due_on": None},
    headers=token(a),
)
check("POST /ops/tasks -> 201", r.status_code == 201, r.text[:300])

r = a.post("/ops/projects", json={"name": "No CSRF", "status": "active"}, headers={})
check("the same call without the CSRF header is refused", r.status_code == 403, str(r.status_code))

r = a.post("/ops/projects", json={"name": "Bad status", "status": "nearly"}, headers=token(a))
check(
    "an unknown status is a 422 naming the field, not a 500 naming a constraint",
    r.status_code == 422 and "status" in r.text,
    f"{r.status_code} {r.text[:200]}",
)

print("\n\033[1m3. Both tiles render from the database\033[0m")
r = a.get("/dashboards/surface")
tiles = {b["key"]: b for b in r.json().get("measured", [])}
check("operations.projects_board carries a figure", "operations.projects_board" in tiles, str(list(tiles)))
check("operations.task_queue carries a figure", "operations.task_queue" in tiles, str(list(tiles)))

board = tiles.get("operations.projects_board", {}).get("figure") or {}
check("it is a count, not a score or an amount", board.get("kind") == "count", str(board)[:200])
check("one project recorded", board.get("recorded") == 1, str(board)[:200])
check("it is open", board.get("open_items") == 1, str(board)[:200])
check(
    "and overdue, because the due date has passed",
    board.get("overdue") == 1,
    str(board)[:200],
)
check(
    "the label says recorded rather than claiming to describe the company",
    "recorded" in str(board.get("label", "")).lower(),
    str(board.get("label")),
)
check(
    "no percentage anywhere in the figure",
    "%" not in str(board) and "percentage" not in board,
    str(board)[:200],
)

queue = tiles.get("operations.task_queue", {}).get("figure") or {}
check("one task recorded, with no due date", queue.get("recorded") == 1, str(queue)[:200])
check("so it is undated and not overdue", (queue.get("undated"), queue.get("overdue")) == (1, 0), str(queue)[:200])

brief = r.json().get("brief", {})
unmeasured = [i["capability_id"] for i in brief.get("items", []) if i["kind"] == "unmeasured"]
check(
    "the brief does not call a tile unmeasured while it shows a number",
    not any(k.startswith("operations.") for k in unmeasured),
    str(unmeasured),
)

r = a.post("/dashboards/operations/narrate", json={"key": "operations.projects_board"}, headers=token(a))
check(
    "a count cannot be narrated and is refused rather than attempted",
    r.status_code == 404,
    f"{r.status_code} {r.text[:150]}",
)

print("\n\033[1m4. Completeness — D29, ADR 0035\033[0m")
board = tiles.get("operations.projects_board", {}).get("figure") or {}
check(
    "before anybody vouches, the figure says so rather than staying silent",
    board.get("complete_as_of") == "",
    str(board)[:200],
)
check(
    "and it declares itself self-reported rather than leaving a client to infer it",
    board.get("self_reported") is True,
    str(board)[:200],
)

r = a.post("/ops/completeness", json={"entity": "projects"}, headers=token(a))
check("POST /ops/completeness -> 201", r.status_code == 201, r.text[:300])

r = a.post(
    "/ops/completeness",
    json={"entity": "projects", "complete_as_of": "2099-01-01"},
    headers=token(a),
)
check("a confirmation dated in the future is refused", r.status_code == 422, str(r.status_code))

r = a.post("/ops/completeness", json={"entity": "invoices"}, headers=token(a))
check("an unknown entity is a 422 naming the field", r.status_code == 422 and "entity" in r.text,
      f"{r.status_code} {r.text[:150]}")

tiles = {x["key"]: x for x in a.get("/dashboards/surface").json().get("measured", [])}
board = tiles.get("operations.projects_board", {}).get("figure") or {}
queue = tiles.get("operations.task_queue", {}).get("figure") or {}
check("the projects figure now carries the date somebody vouched", bool(board.get("complete_as_of")),
      str(board)[:200])
check(
    "confirming projects does not vouch for tasks",
    queue.get("complete_as_of") == "",
    str(queue)[:200],
)
check(
    "and confirming still adds no rate to the figure",
    "%" not in str(board) and "rate" not in board and "percentage" not in board,
    str(board)[:200],
)

print("\n\033[1m5. Another workspace sees none of it\033[0m")
b = founder("b")
r = b.get("/ops")
check(
    "a second company's founder sees an empty ops layer",
    r.status_code == 200 and r.json()["projects"] == [] and r.json()["tasks"] == [],
    r.text[:200],
)

if project_id:
    r = b.delete(f"/ops/projects/{project_id}", headers=token(b))
    check("archiving another workspace's project is accepted and changes nothing", r.status_code == 204, str(r.status_code))
    still = a.get("/ops").json()["projects"]
    check("the project is still there for its owner", len(still) == 1, str(still)[:200])

print("\n\033[1m6. Archive stops it counting without deleting it\033[0m")
if project_id:
    r = a.delete(f"/ops/projects/{project_id}", headers=token(a))
    check("DELETE /ops/projects/{id} -> 204", r.status_code == 204, str(r.status_code))
    tiles = {x["key"]: x for x in a.get("/dashboards/surface").json().get("measured", [])}
    board = tiles.get("operations.projects_board", {}).get("figure") or {}
    check("the projects tile now counts none recorded", board.get("recorded") == 0, str(board)[:200])
    check(
        "the task tile still has its task, so the layer is still in use",
        (tiles.get("operations.task_queue", {}).get("figure") or {}).get("recorded") == 1,
        str(tiles.get("operations.task_queue"))[:200],
    )

print(f"\n\033[1m{ok} passed, {fail} failed\033[0m\n")
sys.exit(1 if fail else 0)
