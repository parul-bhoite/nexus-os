"""The one switch that authorises spending money. `doc/20` A3/A5/A9.

**Why a shared gate rather than one per file.** The live halves are the red team
and the measurement, and they answer different questions — but they share the
only property that matters operationally: running them costs money against a
real model. Two switches would let somebody set one, believe they had run both,
and hand A12 half a picture.

**Why the key is not the gate.** It lives in `.env` and is read through
`Settings`, so `os.environ` never sees it and a developer with a working setup
has one already. Checking it first — the first version of this — skipped every
run on a machine perfectly able to make the call, and blamed a missing key.
`NEXUS_LIVE_EVALS` is what stands between `pytest evals` and a bill, so it is
checked first and on its own.

`evals/` has no `conftest.py`, so the fixture in `tests/conftest.py` that pins
the key empty does not reach here. That is the hazard this module exists for.
"""

from __future__ import annotations

import os

from app.config import get_settings

SWITCH = "NEXUS_LIVE_EVALS"


def gated() -> str | None:
    """A skip reason, or `None` when the caller may spend money."""
    if os.environ.get(SWITCH) != "1":
        return (
            f"{SWITCH} is not 1 — this sends real requests to a real model and "
            f"costs money, so it is opt-in even with a key configured"
        )
    if not get_settings().anthropic_api_key.get_secret_value():
        return "no model key configured — a live eval has nothing to send to"
    return None
