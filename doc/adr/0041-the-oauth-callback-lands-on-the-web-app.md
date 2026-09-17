# 0041 — The OAuth callback lands on the web app, not the API

**Status:** Accepted
**Date:** 17 September 2026
**Depends on:** ADR 0031 (MCP is a transport), ADR 0032 (provider tokens at rest)
**Context:** `doc/14` S9 — giving the connector work a screen

## Context

`routes/connections.py` exposes `GET /connections/{provider}/callback`, which
verifies the signed `state`, exchanges the `code`, seals the refresh token and
returns a `ConnectionOut`. It was written before anything in a browser could
reach it, and the question of *where the vendor sends the person back to* was
never settled — it only became answerable once there was a screen.

The redirect URI is registered in HubSpot's developer portal and must match what
is sent character for character, or the exchange fails at the vendor with a
message about the redirect and nothing about why. So this is a decision that
binds an external registration, not an implementation detail.

## Decision

**The registered redirect URI is a page in the web app** —
`…/connections/{provider}/callback` on the Next.js origin — which forwards the
query string to the API's callback route and renders the result.

Not the API's route directly. Both complete the exchange identically; the
difference is where a person ends up. HubSpot redirects **the browser**, so
pointing it at the API lands a founder on a JSON document at the end of the one
flow in the product where they have just granted access to their whole CRM. That
is the worst possible moment to look like something broke.

Three properties hold it together:

**The query string is forwarded whole and never rebuilt.** `state` is signed and
bound to workspace, person and provider; `code` is single-use. A page that parsed
and reassembled either would put a second copy of a security check where the
first one lives, and the failure mode is an authorisation accepted that should
not have been.

**The exchange runs once.** A `code` is spent on first use, so a re-run on
re-render would ask the vendor to honour it twice and show a founder a failure
for a connection that actually succeeded.

**The page sits outside the app shell.** Somebody arriving here has just come
back from a third party and is one step from done; a full header inviting them
elsewhere is how a connection gets abandoned at the last moment.

## Consequences

- **`.env.example` carries the value to register**, because a redirect URI that
  differs by a trailing slash fails at the vendor and the message says nothing
  useful. Documenting it beside the client id is the only place somebody
  configuring this will look.
- **The web origin is now part of the connector's configuration.** A deployment
  that moves the front end has to re-register the redirect with every provider.
  That is true of the alternative too — it would tie the registration to the API
  origin instead — so it is a cost of OAuth rather than of this choice.
- **The API's callback route stays exactly as it was.** It remains the only place
  that verifies state and seals a token; this adds a page in front of it, not a
  second implementation.
- **A second provider needs no new page.** The route is `[provider]`, and the
  allow-list in the BFF is the one place a new one is admitted.

## Alternatives rejected

**Point the redirect at the API and return a redirect to the web app.** Keeps the
registration on the API origin and adds a hop; the person still briefly lands on
the API, and any failure in the exchange is rendered by a service that has no
templates and no styling.

**Point the redirect at the API and accept the JSON.** Works, costs nothing, and
ends the most sensitive flow in the product on a page that looks like a bug.
