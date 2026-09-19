"""Honour the target's own `robots.txt` before the scan reads its page. G5.

**Confirmed by Parul before building** (`doc/18` marks this step
"confirm before building" — recommended, not required by any ADR). The
authenticated crawl fetches a site the workspace has claimed; this one
fetches a site a stranger merely typed — a different relationship, and the
one extra request is the cheapest available answer to an abuse complaint,
and the thing we would be asked for first.

**Absence is not permission and is not refusal.** No `robots.txt` (a 404,
any other non-200, a timeout, an SSRF-refused robots.txt fetch) means
nothing is known to disallow, so the scan proceeds — a `robots.txt` that
cannot be read is evidence of nothing, not evidence that the target wants no
visitors.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from app.research.crawler import USER_AGENT, FetchError, fetch_page
from app.scan import budget

ROBOTS_TIMEOUT_SECONDS = 5
"""Short, and separate from `budget.TIMEOUT_SECONDS` — a slow or hanging
`robots.txt` must not eat into the time budgeted for the page it guards
access to."""

USER_AGENT_TOKEN = USER_AGENT.split("/", 1)[0]
"""The bare product token (`NexusOS-Audit`), not the full descriptive
`USER_AGENT` string with its version and URL.

`urllib.robotparser.Entry.applies_to` truncates *its* `useragent` argument to
the part before the first `/` before comparing — so passing the full
`USER_AGENT` string to `can_fetch` never matches a `robots.txt` written the
normal way, `User-agent: NexusOS-Audit`, because the entry's agent string is
compared against that truncated token, not against the string actually
passed in. Verified by hand: a robots.txt disallowing the *full* `USER_AGENT`
string silently permitted everything, because the entry's own agent was
never the substring being matched against.
"""


class ScanDisallowedError(Exception):
    """`robots.txt` disallows our user agent on this path.

    Not `FetchError` and not an SSRF refusal — a courtesy this scan chooses
    to extend, not a defence against an attack — so it is its own error
    rather than borrowing a shape that means something else.
    """


def _robots_url(raw_url: str) -> str:
    parts = urlsplit(raw_url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


async def check_allowed(raw_url: str) -> None:
    """Raise `ScanDisallowedError` if `raw_url`'s `robots.txt` disallows our
    user agent on its path. Returns silently otherwise."""
    try:
        page = await fetch_page(
            _robots_url(raw_url),
            max_bytes=budget.MAX_BYTES,
            timeout_seconds=ROBOTS_TIMEOUT_SECONDS,
            max_redirects=budget.MAX_REDIRECTS,
        )
    except FetchError:
        return  # unreachable, refused, timed out, or not text — treat as absent

    if page.status_code != 200:
        return  # a 404 (or any other non-200) is the ordinary "no robots.txt"

    parser = RobotFileParser()
    parser.parse(page.html.splitlines())

    path = urlsplit(raw_url).path or "/"
    if not parser.can_fetch(USER_AGENT_TOKEN, path):
        raise ScanDisallowedError("This site's robots.txt asks us not to read this page.")
