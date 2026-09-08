"""A ceiling on request bodies, applied before anything parses one.

Finding B4. A 50 MB JSON body was accepted, buffered and parsed, and only then
refused by field validation — `phone` has a 32-character cap, so the rejection
was correct and arrived after the whole 50 MB was resident. Validation cannot be
the first line here: by the time Pydantic sees a value, the bytes are already in
memory, and a handful of concurrent large bodies is a memory-amplification lever
with no valid account behind it.

**Pure ASGI, not `@app.middleware("http")`.** That decorator is
`BaseHTTPMiddleware`, which materialises the request to hand it to a callable —
so a limit written there would have to read the body to measure it, which is the
thing being prevented. This wraps `receive` instead and counts chunks as they
arrive, so an oversized body is refused part-way through rather than after it
lands.

**Both the header and the stream are checked, and the stream is the real one.**
`Content-Length` is the cheap path: it refuses before a single byte of body is
read. It is also client-supplied and omissible — a chunked request carries no
length at all — so the header check is an optimisation and the running total is
the enforcement. Trusting the header alone is a limit that anybody can opt out
of by not declaring one.

**Two limits, because one would have to be the larger.** Document upload
legitimately carries 25 MiB, and every other endpoint on this API takes a small
JSON form. A single limit generous enough for the first is no limit at all for
the second, which is where the finding was.

**It is not a second implementation of the upload limit.** `MAX_FILE_BYTES` is
imported rather than restated, and the upload ceiling here is deliberately
*above* it: `app/documents/limits.py` is the authority on how large a file may
be, and it answers with a message about splitting the file. This only has to
stop a body nobody could have meant, so it adds slack for multipart framing and
leaves the real refusal where it belongs. Two implementations of one limit is
how a client says fine and the server says too big.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, Final

from app.documents.limits import MAX_FILE_BYTES
from app.logging import get_logger

log = get_logger(__name__)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

MAX_JSON_BODY_BYTES: Final = 256 * 1024
"""Every endpoint except document upload.

Generous on purpose. The largest legitimate body on this API is a form of prose
fields — `/onboarding/agent/describe` is three fields of 2,000 characters, and a
brief confirmation is a handful of corrections — so the real requirement is a few
tens of kilobytes. A quarter of a megabyte leaves room for an endpoint nobody
has written yet without leaving room for the finding: it is a ~200x reduction
from the 50 MB that was accepted, and still far below anything that costs
memory when a few arrive at once.

Chosen at the top of the range `doc`-level review suggested (64-256 KB) because
the failure mode of too tight is worse than of too loose here: too loose is a
bounded memory cost, and too tight is a legitimate request refused with a
message about size that its author cannot act on.
"""

MAX_UPLOAD_BODY_BYTES: Final = MAX_FILE_BYTES + 512 * 1024
"""Document upload, with room for multipart framing.

Above `MAX_FILE_BYTES`, never equal to it. A 25 MiB file arrives inside a
multipart envelope — boundaries, per-part headers, the `consent` field — so a
body at exactly the file limit is slightly larger than the file. Setting these
equal would refuse a file the product accepts, with the wrong error, from the
wrong layer.
"""

_METHODS_WITH_BODIES: Final = frozenset({"POST", "PUT", "PATCH"})

_UPLOAD_PATHS: Final = frozenset({"/documents"})
"""Exact paths permitted the larger ceiling.

Exact rather than a prefix match. `/documents` is the upload; every other route
under it — `/documents/asks`, `/documents/{id}/download`, the review queue — is
a GET or a small JSON body, and a prefix would hand all of them a 25 MiB
allowance for no reason.
"""


class BodySizeLimit:
    """Refuse a request body over the ceiling for its route."""

    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.app = app

    def _limit_for(self, scope: Scope) -> int:
        path = scope.get("path", "")
        return MAX_UPLOAD_BODY_BYTES if path in _UPLOAD_PATHS else MAX_JSON_BODY_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("method") not in _METHODS_WITH_BODIES:
            await self.app(scope, receive, send)
            return

        limit = self._limit_for(scope)

        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            # Refused before the body is read at all. An honest client that
            # declares its length gets the cheapest possible rejection.
            await self._refuse(send, limit, scope, declared=declared)
            return

        received = 0
        refused = False

        # **The refusal is sent from here, not raised.** The first version of
        # this raised a custom exception out of `receive` and answered in an
        # `except` clause, and FastAPI silently defeated it: `get_request_handler`
        # wraps body parsing in `except Exception` and converts *anything* it
        # catches into `HTTPException(400, "There was an error parsing the
        # body")`. So a 512 KB chunked body came back 400 and the limit looked
        # like it was working while the whole body had been read. Nothing that
        # depends on an exception surviving a framework's error handling can be
        # an enforcement boundary.
        #
        # Instead: answer 413 immediately, hand the handler an
        # `http.disconnect` so it unwinds the way it already knows how, and drop
        # whatever it produces on the way out.

        async def counting_receive() -> Message:
            nonlocal received, refused
            if refused:
                return {"type": "http.disconnect"}

            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b"") or b"")
                if received > limit:
                    refused = True
                    await self._refuse(send, limit, scope, declared=None, read=received)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            # After a refusal the client already has a complete response, so a
            # second `http.response.start` would be a protocol error. The
            # handler is not wrong to try — it is answering a disconnect it did
            # not ask for — so its output is dropped rather than treated as a
            # fault.
            if refused:
                return
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            # Only ever swallowed *after* a refusal, and only because the
            # unwind is one this middleware caused. Without this the exception
            # reaches `ServerErrorMiddleware` — which sits outside here and
            # holds the real `send` — and it would emit a 500 on top of the 413
            # already written.
            if not refused:
                raise
            log.debug("request.body_too_large.handler_unwound", path=scope.get("path", ""))

    async def _refuse(
        self,
        send: Send,
        limit: int,
        scope: Scope,
        *,
        declared: int | None,
        read: int | None = None,
    ) -> None:
        log.info(
            "request.body_too_large",
            path=scope.get("path", ""),
            limit_bytes=limit,
            # Which of the two caught it. A flood that omits `Content-Length`
            # is a different client from one that declares an honest 50 MB, and
            # only the header case is refused before the bytes arrive.
            declared_bytes=declared,
            read_bytes=read,
        )
        body = json.dumps(
            {
                "detail": {
                    "error": "request_too_large",
                    "message": (
                        f"That request body is over the {limit // 1024} KB limit for this "
                        "endpoint."
                    ),
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    # Nothing about a refusal is worth caching, and a cached
                    # 413 against a path would outlive the request that earned
                    # it.
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _declared_length(scope: Scope) -> int | None:
    """`Content-Length`, if the client sent one that is a number.

    A malformed value is treated as absent rather than as an error: the running
    total below is the enforcement either way, and rejecting the request here
    would turn a header quirk into a failure on a body that may be perfectly
    small.
    """
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None
