# 0064. The document parser hardens the stdlib XML stack, not each library

- **Status:** Accepted
- **Date:** 22 September 2026
- **Deciders:** Parul (from the E2E defect register, L-05)
- **Implements:** E2E defect register L-05
- **Affects:** `app/documents/parse.py`, `services/api/pyproject.toml`, the
  document upload path in `app/routes/documents.py`

## Context

Uploaded documents are parsed by dispatching on the filename extension into
`openpyxl`, `python-docx` and `pypdf`. Those libraries — and the Office Open XML
formats in general — parse XML through Python's standard-library stack
(`xml.etree`, `xml.sax`, `xml.dom.minidom`, and the expat/lxml machinery beneath).

The stdlib parsers resolve external entities and expand internal entities by
default. Over attacker-controlled input — any member can upload a document — that
is two reachable denial-of-service / disclosure vectors:

- **Entity expansion ("billion laughs"):** a small file whose entities expand to
  gigabytes, exhausting memory and, because L-05 also found the parse ran inline
  on the event loop, stalling every other request in the process.
- **External entity injection (XXE):** a well-formed document that references a
  local file or an internal URL the parser then fetches.

At the time of the finding, `defusedxml` was not a dependency and the upload path
had no protection against either. Adding a security dependency and choosing *where*
the hardening lives is a technology and trust-boundary decision, so it is recorded
here even though the register prescribed the library by name.

## Options considered

### A. `defusedxml` + `defuse_stdlib()` — patch the shared stdlib layer once

`defuse_stdlib()` monkey-patches the standard-library parsers in place, so the
third-party libraries that call them transitively (openpyxl, python-docx) inherit
the protection with no change to their own code. It is the mitigation the Python
security documentation itself points to.

### B. Configure each parser by hand

Reach into openpyxl / python-docx / pypdf and disable entity resolution
per-library. Requires knowing each library's internal parser wiring and re-checking
it on every upstream bump; it breaks silently when an upstream changes how it
parses.

### C. Write our own hardened XML wrapper

No new dependency, full control — but substantial code that would still have to
intercept the same stdlib entry points `defuse_stdlib()` already covers, i.e.
reimplementing the library badly.

### D. Rely on the file-size cap alone

A size cap stops neither vector: the entity-expansion *file* is small, and the XXE
file is well-formed. Rejected as not addressing the finding.

## Decision

Option A. `defusedxml` is a runtime dependency, and `app/documents/parse.py` calls
`defuse_stdlib()` once at import, hardening the standard-library XML parsers
process-wide before any document is parsed. This sits alongside the other L-05
mitigations recorded in the same change: the parse now runs off the event loop via
`anyio.to_thread.run_sync` under a bounded `CapacityLimiter` (the argon2 limiter
pattern), and a zip-bomb guard rejects `.docx`/`.pptx`/`.xlsx` whose declared
uncompressed size is too large before any parser touches the content.

## Reasoning

The vulnerable parsing happens *inside* libraries we do not control, so the
hardening has to live at the one layer they all share. That is what makes B and C
lose: both would chase each library's parser configuration and re-verify it on
every version bump, and the moment a new format handler is added it starts
unprotected. `defuse_stdlib()` protects every current and future stdlib XML
consumer in the process at once. `defusedxml` is also the name the ecosystem
already standardises on, so a newcomer meets a known mitigation rather than a
bespoke wrapper, and its footprint (tiny, pure-Python, no transitive deps) is far
below the cost of hand-rolling the same interception. The consciously accepted
tradeoff is that a process-wide monkey-patch is action-at-a-distance — see the
consequences.

## Consequences

- Entity expansion and XXE are closed for every stdlib XML consumer in the API
  process, including handlers added later, with no per-call work at the parse
  sites.
- `defuse_stdlib()` imports a deprecated `cElementTree` shim and emits an
  unsuppressed `DeprecationWarning`. Because the suite sets
  `filterwarnings = ["error"]`, that warning becomes a collection-time error for
  every module importing `app.documents.parse`. It is contained by wrapping **only
  that one call** in a local `warnings.catch_warnings()` /
  `simplefilter("ignore", DeprecationWarning)` — the project-wide policy is left
  strict, and the reason is documented inline at the call site.
- `types-defusedxml` does not cover `defuse_stdlib`, so a `[[tool.mypy.overrides]]`
  entry with `ignore_missing_imports` was added for `defusedxml.*`; the
  `types-defusedxml` dev dependency was intentionally not kept, as it made
  type-checking worse.
- The patch is implicit: anyone debugging XML behaviour must know
  `defuse_stdlib()` ran at import. The single call site and this ADR are the record
  of that.

## Revisit trigger

Reopen if `defusedxml` stops being maintained or lags a Python release we need; or
the deprecated-shim `DeprecationWarning` becomes a hard removal in a future Python
that breaks `defuse_stdlib()` (evaluate per-parser hardening, option B, against
whatever the ecosystem has moved to by then); or XML parsing moves into an isolated
subprocess/sandbox, which would make the in-process patch redundant.
