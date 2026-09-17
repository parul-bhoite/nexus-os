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

from datetime import date, timedelta
from uuid import uuid4

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
    client = httpx.Client(base_url=API, timeout=180.0)

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

print("\n\033[1m5. Milestones and issues — S10.3\033[0m")
# Relative to today, never hardcoded. A literal date passes until the day it
# stops being in the future, and then reads as a defect in the calculator.
AHEAD = (date.today() + timedelta(days=60)).isoformat()
PASSED = (date.today() - timedelta(days=30)).isoformat()

r = a.post(
    "/ops/milestones",
    json={"title": "Glazing signed off", "project_id": project_id, "planned_on": AHEAD},
    headers=token(a),
)
check("POST /ops/milestones -> 201", r.status_code == 201, r.text[:300])

r = a.post(
    "/ops/milestones",
    json={"title": "Slab poured", "project_id": project_id, "planned_on": PASSED},
    headers=token(a),
)
check("a second milestone, dated in the past", r.status_code == 201, r.text[:300])

r = a.post(
    "/ops/milestones",
    json={"title": "Orphan", "project_id": str(uuid4()), "planned_on": "2026-02-01"},
    headers=token(a),
)
check("a milestone on a project that is not ours is a 404", r.status_code == 404, str(r.status_code))

for severity in ("high", "low", "low"):
    a.post(
        "/ops/issues",
        json={"title": f"Snag {severity}", "severity": severity, "project_id": project_id},
        headers=token(a),
    )
r = a.post("/ops/issues", json={"title": "Bad", "severity": "catastrophic"}, headers=token(a))
check("an unknown severity is a 422 naming the field", r.status_code == 422 and "severity" in r.text,
      f"{r.status_code} {r.text[:150]}")

tiles = {x["key"]: x for x in a.get("/dashboards/surface").json().get("measured", [])}
milestones = tiles.get("operations.milestone_timeline", {}).get("figure") or {}
register = tiles.get("operations.issue_register", {}).get("figure") or {}

check("operations.milestone_timeline carries a figure", bool(milestones), str(list(tiles)))
check("two milestones recorded, one of them past its planned date",
      (milestones.get("recorded"), milestones.get("overdue")) == (2, 1), str(milestones)[:200])
check("a milestone always has a date, so none is undated", milestones.get("undated") == 0,
      str(milestones)[:200])

check("operations.issue_register carries a figure", bool(register), str(list(tiles)))
check("three issues recorded", register.get("recorded") == 3, str(register)[:200])
bands = {b["label"]: b["count"] for b in register.get("breakdown", [])}
check("split by severity, worst first, every band present",
      [b["label"] for b in register.get("breakdown", [])] == ["high", "medium", "low"], str(bands))
check("and the counts are right", bands == {"high": 1, "medium": 0, "low": 2}, str(bands))
check("the bands are counts and add up to what is open",
      sum(bands.values()) == register.get("open_items"), f"{bands} vs {register.get('open_items')}")
check("still no percentage anywhere", "%" not in str(register), str(register)[:200])

check("only projects and tasks have no breakdown",
      (tiles.get("operations.projects_board", {}).get("figure") or {}).get("breakdown") == [],
      str(tiles.get("operations.projects_board"))[:150])

r = a.post("/ops/completeness", json={"entity": "issues"}, headers=token(a))
check("completeness can now be confirmed for issues too", r.status_code == 201, r.text[:200])

print("\n\033[1m6. On-time dispatch — the first ops rate, S10.4\033[0m")
SENT_LATE = (date.today() - timedelta(days=3)).isoformat()
PROMISED = (date.today() - timedelta(days=5)).isoformat()

for ref, sent in (("SO-1", PROMISED), ("SO-2", SENT_LATE), ("SO-3", None)):
    a.post(
        "/ops/dispatches",
        json={"reference": ref, "promised_on": PROMISED, "dispatched_on": sent},
        headers=token(a),
    )

tiles = {x["key"]: x for x in a.get("/dashboards/surface").json().get("measured", [])}
rate = tiles.get("operations.on_time_dispatch", {}).get("figure") or {}
check("operations.on_time_dispatch carries a figure", bool(rate), str(list(tiles)))
check("it is a rate", rate.get("kind") == "rate", str(rate)[:200])
check("and it refuses, because nobody has vouched for the record",
      rate.get("refused") == "unvouched", str(rate)[:250])
check("**no percentage is served under a refusal**", rate.get("percentage") is None, str(rate)[:250])
check("nor half a fraction", (rate.get("numerator"), rate.get("denominator")) == (None, None),
      str(rate)[:250])
check("but the counts are, because they are true either way",
      (rate.get("outstanding"), rate.get("overdue")) == (1, 1), str(rate)[:250])

a.post("/ops/completeness", json={"entity": "dispatches"}, headers=token(a))
tiles = {x["key"]: x for x in a.get("/dashboards/surface").json().get("measured", [])}
rate = tiles.get("operations.on_time_dispatch", {}).get("figure") or {}
check("vouched, it now refuses for the other reason — nobody has set the rule",
      rate.get("refused") == "no_rule", str(rate)[:250])
check("and still no percentage", rate.get("percentage") is None, str(rate)[:250])

r = a.put("/ops/dispatch-rule", json={"grace_days": -1}, headers=token(a))
check("a negative grace is refused", r.status_code == 422, str(r.status_code))
r = a.put("/ops/dispatch-rule", json={"grace_days": 0}, headers=token(a))
check("PUT /ops/dispatch-rule -> 200", r.status_code == 200, r.text[:200])

tiles = {x["key"]: x for x in a.get("/dashboards/surface").json().get("measured", [])}
rate = tiles.get("operations.on_time_dispatch", {}).get("figure") or {}
check("both gates open, the rate appears", rate.get("refused") == "", str(rate)[:250])
check("one of the two that went out was on time", rate.get("percentage") == 50.0, str(rate)[:250])
check("with both halves of the fraction",
      (rate.get("numerator"), rate.get("denominator")) == (1, 2), str(rate)[:250])
check("the outstanding order is not in the denominator", rate.get("outstanding") == 1,
      str(rate)[:250])
check("and the rule travels with the figure", rate.get("grace_days") == 0, str(rate)[:250])

r = a.put("/ops/dispatch-rule", json={"grace_days": 5}, headers=token(a))
tiles = {x["key"]: x for x in a.get("/dashboards/surface").json().get("measured", [])}
rate = tiles.get("operations.on_time_dispatch", {}).get("figure") or {}
check("widening the grace changes the figure, because the rule is the customer's",
      rate.get("percentage") == 100.0, str(rate)[:250])
check("and the overdue count moves with it", rate.get("overdue") == 0, str(rate)[:250])

r = a.post("/dashboards/operations/narrate", json={"key": "operations.on_time_dispatch"},
           headers=token(a))
check("a rate is still refused for narration (ADR 0036)", r.status_code == 404, str(r.status_code))

print("\n\033[1m7. Stock and suppliers — S10.5\033[0m")
for name, on_hand, minimum in (("Bolts", 2, 10), ("Nuts", 50, 10), ("Glue", 0, 40)):
    a.post(
        "/ops/stock",
        json={"name": name, "on_hand": on_hand, "minimum": minimum},
        headers=token(a),
    )
r = a.post("/ops/stock", json={"name": "Bad", "on_hand": -1, "minimum": 1}, headers=token(a))
check("a negative quantity is refused", r.status_code == 422, str(r.status_code))

for name, spend in (("Al Bahja", 600_00), ("Gulf Traders", 400_00), ("Unpriced Co", None)):
    a.post("/ops/suppliers", json={"name": name, "spend_minor": spend}, headers=token(a))

tiles = {x["key"]: x for x in a.get("/dashboards/surface").json().get("measured", [])}
stock = tiles.get("operations.stock_levels", {}).get("figure") or {}
risk = tiles.get("operations.supplier_risk", {}).get("figure") or {}

check("operations.stock_levels carries a figure", bool(stock), str(list(tiles)))
check("it is a count, because a level comparison is not a rate",
      stock.get("kind") == "count", str(stock)[:200])
check("three lines recorded, two under their minimum",
      (stock.get("recorded"), stock.get("open_items")) == (3, 2), str(stock)[:250])
check("and it says what the second number means",
      stock.get("open_label") == "below their minimum", str(stock)[:250])
check("ranked by shortfall rather than alphabetically",
      [b["label"] for b in stock.get("breakdown", [])] == ["Glue", "Bolts"],
      str(stock.get("breakdown")))
check("no percentage on the stock tile", "%" not in str(stock), str(stock)[:200])

check("operations.supplier_risk carries a figure", bool(risk), str(list(tiles)))
check("it is a rate", risk.get("kind") == "rate", str(risk)[:200])
check("and it refuses until the supplier list is vouched for",
      risk.get("refused") == "unvouched", str(risk)[:250])
check("the unpriced supplier is reported, not dropped", risk.get("excluded") == 1,
      str(risk)[:250])

a.post("/ops/completeness", json={"entity": "suppliers"}, headers=token(a))
tiles = {x["key"]: x for x in a.get("/dashboards/surface").json().get("measured", [])}
risk = tiles.get("operations.supplier_risk", {}).get("figure") or {}
check("vouched, the share appears with no second gate to pass",
      risk.get("refused") == "" and risk.get("percentage") == 60.0, str(risk)[:250])
check("it is declared as money, so a client never prints minor units",
      risk.get("unit") == "money", str(risk)[:250])
# **`POST /companies` deliberately does not store `reporting_currency`** — the
# fact is asked later as a constrained choice — so a workspace this young has
# money it cannot format. The share is true either way and the tile shows it
# alone; inventing a currency here would be a fact nobody gave.
check("and carries no currency until the workspace has set one",
      risk.get("currency") is None, str(risk)[:250])
check("the denominator is named", bool(risk.get("denominator_label")), str(risk)[:250])
check("vouching for suppliers did not vouch for stock",
      (tiles.get("operations.stock_levels", {}).get("figure") or {}).get("complete_as_of") == "",
      str(tiles.get("operations.stock_levels"))[:200])

print("\n\033[1m8. Deals-lite — D30, one table partitioned by provenance\033[0m")
for name, amount in (("Villa fit-out", 50_000), ("Retail unit", 25_000), ("No price yet", None)):
    r = a.post(
        "/ops/deals",
        json={"name": name, "amount_minor": amount, "currency": "OMR" if amount else None},
        headers=token(a),
    )
check("POST /ops/deals -> 201", r.status_code == 201, r.text[:300])

r = a.post("/ops/deals", json={"name": "Half", "amount_minor": 100}, headers=token(a))
check("an amount with no currency is refused", r.status_code == 422, str(r.status_code))

tiles = {x["key"]: x for x in a.get("/dashboards/surface").json().get("measured", [])}
lite = tiles.get("sales.deals_lite", {}).get("figure") or {}
check("sales.deals_lite carries a figure", bool(lite), str(list(tiles)))
check("it is an amount, the same kind the CRM tile serves",
      lite.get("kind") == "amount", str(lite)[:200])
check("three deals counted, the unpriced one among them", lite.get("count") == 3,
      str(lite)[:250])
check("and it is totalled from the two that have a price",
      lite.get("total_minor") == 75_000 and lite.get("uncounted") == 1, str(lite)[:250])
check("**it declares itself self-reported**", lite.get("self_reported") is True,
      str(lite)[:250])

# **The partition.** These deals are `provider = 'nexus'` rows of `crm_deal`, and
# the CRM tile reads the same table. Without the `provider <> 'nexus'` clause it
# would report somebody's own typing as though a provider had said so.
check("and the CRM pipeline tile does not see them at all",
      "sales.pipeline_board" not in tiles, str(list(tiles)))

print("\n\033[1m9. The compositions — S10.7, ADR 0040 (D31)\033[0m")
tiles = {x["key"]: x for x in a.get("/dashboards/surface").json().get("measured", [])}
drivers = tiles.get("operations.score_drivers", {}).get("figure") or {}
todo = tiles.get("executive.todays_priorities", {}).get("figure") or {}

check("operations.score_drivers carries a figure", bool(drivers), str(list(tiles)))
check("it is a drivers composition", drivers.get("kind") == "drivers", str(drivers)[:200])
check("**and it carries no score and no delta**",
      "percentage" not in drivers and "score" not in drivers and "delta" not in drivers,
      str(drivers)[:250])
check("it names the figures a score would have averaged",
      len(drivers.get("inputs", [])) == 7, str(drivers.get("inputs"))[:200])
check("and says why there is not one", "deliberate" in drivers.get("reason", ""),
      str(drivers.get("reason"))[:200])

r = a.post("/dashboards/operations/narrate", json={"key": "operations.score_drivers"},
           headers=token(a))
check("a composition cannot be narrated — it has no number to explain",
      r.status_code == 404, str(r.status_code))

check("executive.todays_priorities carries a figure", bool(todo), str(list(tiles)))
check("it is a priorities composition", todo.get("kind") == "priorities", str(todo)[:200])
check("the ranked list holds only things past a date",
      all("past" in i["detail"] for i in todo.get("overdue", [])), str(todo.get("overdue"))[:250])
check("ranked worst first",
      [i["detail"] for i in todo.get("overdue", [])]
      == sorted((i["detail"] for i in todo.get("overdue", [])),
                key=lambda d: -int(d.split()[0])),
      str(todo.get("overdue"))[:250])
check("what is not measured in days sits beside it, never in it",
      all("past" not in i["detail"] for i in todo.get("beside", [])),
      str(todo.get("beside"))[:250])
check("and nothing is totalled",
      "total" not in todo and "score" not in todo, str(todo)[:200])

print("\n\033[1m10. Another workspace sees none of it\033[0m")
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

print("\n\033[1m11. Archive stops it counting without deleting it\033[0m")
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
