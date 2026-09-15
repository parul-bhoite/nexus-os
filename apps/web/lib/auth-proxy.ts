import { NextResponse } from 'next/server'

/**
 * Server-side proxy for the auth endpoints.
 *
 * The browser never learns the API's address and there is no CORS surface —
 * the reasoning the Preview proxy was built on, and the reason this pattern
 * outlived it. For auth it buys something further.
 * The session cookie is `httponly` and `SameSite=Lax`, and both properties only
 * hold if the cookie belongs to the origin the browser is actually talking to.
 * Calling the API directly from the page would make every auth request
 * cross-origin, which means CORS with credentials and `SameSite=None` — and
 * `SameSite=None` is precisely the protection the API deliberately relies on
 * (see `app/auth/csrf.py`). Proxying keeps the cookie first-party.
 *
 * Two directions of forwarding, and both matter:
 *
 * - **Upstream**: the browser's `Cookie` header and its `X-CSRF-Token`. Without
 *   the cookie the API cannot resolve the session; without the header its
 *   double-submit check rejects every state-changing call.
 * - **Downstream**: `Set-Cookie`. Building a fresh response drops all upstream
 *   headers, and dropping this one means login appears to succeed while setting
 *   no session at all.
 *
 * This route adds no checks of its own. Every guard — password verification,
 * session resolution, CSRF, membership visibility — lives in the API, and this
 * file must never be mistaken for the place they happen.
 */

const API_BASE = process.env.NEXUS_API_BASE_URL ?? 'http://127.0.0.1:8000'

/** Comfortably above a round trip to a managed database, well below a hang.
 *
 * **Correct only for routes that do not call a model.** A single Haiku call is
 * four to five seconds and a Sonnet one can be twenty, so a route that invokes
 * a skill and inherits this default is a timeout waiting for a slow day — see
 * `MODEL_TIMEOUT_MS`. */
const TIMEOUT_MS = Number(process.env.NEXUS_PROXY_TIMEOUT_MS ?? 30_000)

/**
 * For a route that invokes one skill.
 *
 * **Three model-backed onboarding routes were on the database default**, and a
 * browser walkthrough hit it: the brief step aborted at thirty seconds while
 * the API was still working, and the founder was told the service could not be
 * reached. `/onboarding/agent/answer` was the worst of them — it can make up to
 * `MAX_REJECTIONS` question-generation calls in one request.
 *
 * Named rather than sprinkled as a literal, because the failure it prevents is
 * somebody adding a seventh model-backed route and inheriting the number meant
 * for a database read. `lib/__tests__/auth-proxy.test.ts` asserts every such
 * route uses it.
 */
export const MODEL_TIMEOUT_MS = Number(process.env.NEXUS_PROXY_MODEL_TIMEOUT_MS ?? 90_000)

/**
 * Why 30 seconds and not 15 (finding #23).
 *
 * Fifteen was chosen against a local Postgres answering in microseconds. It is
 * below what real requests actually take when the API and the database are far
 * apart: from a laptop against Neon in `us-east-1` a round trip is ~0.35s, and
 * `POST /companies` and `GET /dashboards` each spend twenty-five to thirty of
 * them — so the two most important requests in the product 503'd in the
 * browser while CI stayed green, because CI's database is local.
 *
 * **This raises the ceiling; it does not fix the round trips.** #23 stays open
 * for that, and it is the real defect — in production the API and database are
 * co-located and the same request costs milliseconds, so a timeout this high
 * should never be reached. It exists so development against a remote database
 * is possible, and so a slow request fails as slow rather than as broken.
 *
 * Configurable because the right value differs by deployment, and a constant
 * compiled into the bundle cannot be tuned by the person who feels the problem.
 */

/** Uploads get longer still. A 25 MB file on a slow connection is a slow
 *  request, not a broken one, and even the raised JSON budget would refuse the
 *  uploads most worth waiting for. */
const UPLOAD_TIMEOUT_MS = 120_000

/**
 * Headers copied from the browser to the API. An allowlist rather than a
 * pass-through: forwarding whatever arrives would let a caller set
 * `X-Forwarded-For` and speak as another address, which the API trusts from this
 * hop.
 */
function upstreamHeaders(request: Request, json: boolean): Headers {
  const headers = new Headers()
  if (json) headers.set('Content-Type', 'application/json')

  const cookie = request.headers.get('cookie')
  if (cookie) headers.set('Cookie', cookie)

  const csrf = request.headers.get('x-csrf-token')
  if (csrf) headers.set('X-CSRF-Token', csrf)

  return headers
}

/**
 * Copies `Set-Cookie` from the API's response.
 *
 * `getSetCookie()` rather than `get('set-cookie')`: login sets two cookies, and
 * `get` collapses them into one comma-joined string that no browser can parse
 * back into two. Cookie values may legitimately contain commas, so splitting is
 * not a fix.
 */
function forwardCookies(from: Response, to: Headers): void {
  for (const cookie of from.headers.getSetCookie()) {
    to.append('set-cookie', cookie)
  }
}

export type ProxyOptions = {
  /** Path on the API, e.g. `/auth/login`. */
  path: string
  method: 'GET' | 'POST' | 'PUT'
  /** Body to send. Omit for GET. */
  body?: unknown
  /** Shown if the API cannot be reached at all. */
  unavailable: string
  /**
   * Override the default ceiling for one route.
   *
   * The default is sized for a database round trip. Guided onboarding's `start`
   * is a site crawl followed by two model calls at high effort, which is a
   * different order of magnitude — left at the default it aborts mid-think and
   * the browser reports the API as unreachable when it is simply still working.
   */
  timeoutMs?: number
}

export async function proxyToApi(
  request: Request,
  { path, method, body, unavailable, timeoutMs }: ProxyOptions,
): Promise<NextResponse> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs ?? TIMEOUT_MS)

  try {
    const upstream = await fetch(`${API_BASE}${path}`, {
      method,
      headers: upstreamHeaders(request, body !== undefined),
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      cache: 'no-store',
      // The API sets the cookies; this fetch must not keep them itself.
      redirect: 'manual',
    })

    const headers = new Headers()
    forwardCookies(upstream, headers)
    headers.set('cache-control', 'no-store')

    // 204 carries no body, and giving it one is a protocol error.
    if (upstream.status === 204) {
      return new NextResponse(null, { status: 204, headers })
    }

    const payload = await upstream.json().catch(() => ({ detail: 'Unexpected response.' }))
    return NextResponse.json(payload, { status: upstream.status, headers })
  } catch (caught: unknown) {
    // **A timeout is not an unreachable service, and saying so was a lie.**
    //
    // Every failure here used to produce the caller's `unavailable` sentence —
    // for onboarding, "Cannot reach the onboarding service right now." A
    // browser walkthrough hit it while the API was working perfectly: one
    // request had spent 37 seconds retrying a rejected question, the abort
    // below fired at 30, and the founder was told the service was unreachable.
    // It was not. It was slow, it finished, and its answer arrived for a client
    // that had already been told a different story.
    //
    // The two need different words because they need different actions: an
    // unreachable service is worth reporting, a slow one is worth waiting for.
    // `AbortError` is the only thing `controller.abort()` produces, so the
    // distinction costs one `instanceof`.
    const timedOut = caught instanceof DOMException && caught.name === 'AbortError'
    return NextResponse.json(
      {
        detail: timedOut
          ? 'That took longer than we allow for one request. Nothing is broken and nothing '
            + 'was lost — this often finishes on a second try.'
          : unavailable,
      },
      { status: timedOut ? 504 : 503 },
    )
  } finally {
    clearTimeout(timeout)
  }
}

/** Reads and lightly shapes a JSON body, without validating it. The API does that. */
export async function readJson(request: Request): Promise<Record<string, unknown> | null> {
  try {
    const body = await request.json()
    return body && typeof body === 'object' ? (body as Record<string, unknown>) : null
  } catch {
    return null
  }
}

/**
 * Forwards a multipart upload to the API, body untouched.
 *
 * `proxyToApi` cannot do this: it JSON-stringifies whatever it is given, which
 * turns a file into the string `[object Object]` and loses the boundary the
 * multipart parser needs. So the body streams through as-is and the API's own
 * `UploadFile` parser sees exactly what the browser sent.
 *
 * **`Content-Type` is copied from the request, not set here.** It carries the
 * multipart boundary, which is generated per-request by the browser — writing a
 * fixed one would break every upload, and omitting it makes the API read the
 * body as a single unnamed blob.
 *
 * The timeout is longer than the JSON one. A 25 MB file over a hotel connection
 * is a slow request rather than a broken one, and cutting it off at fifteen
 * seconds would refuse the uploads most worth waiting for.
 */
export async function proxyUpload(
  request: Request,
  { path, unavailable }: { path: string; unavailable: string },
): Promise<NextResponse> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS)

  try {
    const headers = new Headers()
    const cookie = request.headers.get('cookie')
    if (cookie) headers.set('Cookie', cookie)
    const csrf = request.headers.get('x-csrf-token')
    if (csrf) headers.set('X-CSRF-Token', csrf)
    const contentType = request.headers.get('content-type')
    if (contentType) headers.set('Content-Type', contentType)

    const upstream = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers,
      body: await request.arrayBuffer(),
      signal: controller.signal,
      cache: 'no-store',
      redirect: 'manual',
    })

    const responseHeaders = new Headers()
    forwardCookies(upstream, responseHeaders)
    responseHeaders.set('cache-control', 'no-store')

    const payload = await upstream.json().catch(() => ({ detail: 'Unexpected response.' }))
    return NextResponse.json(payload, { status: upstream.status, headers: responseHeaders })
  } catch {
    return NextResponse.json({ detail: unavailable }, { status: 503 })
  } finally {
    clearTimeout(timeout)
  }
}
