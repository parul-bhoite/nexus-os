import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MODEL_TIMEOUT_MS } from '@/lib/auth-proxy'

/**
 * The BFF proxy, tested where Playwright cannot reach.
 *
 * This layer exists so the browser never holds an API token and never talks to
 * the API directly. Everything it does is a *security* behaviour rather than a
 * visible one, which means the journey passes whether or not it is right: a
 * proxy that forwarded the wrong cookies, or collapsed two `Set-Cookie` headers
 * into one, would still render every page.
 *
 * So these assert the things that fail silently.
 */

const upstream = vi.fn()

beforeEach(() => {
  vi.resetModules()
  vi.stubGlobal('fetch', upstream)
  upstream.mockReset()
})
afterEach(() => {
  vi.unstubAllGlobals()
})

function apiResponse(body: unknown, init: { status?: number; cookies?: string[] } = {}): Response {
  const headers = new Headers()
  for (const cookie of init.cookies ?? []) headers.append('set-cookie', cookie)
  return {
    status: init.status ?? 200,
    headers: {
      ...headers,
      getSetCookie: () => init.cookies ?? [],
    } as unknown as Headers,
    json: async () => body,
  } as Response
}

function request(headers: Record<string, string> = {}): Request {
  return new Request('http://localhost:3001/api/whatever', {
    method: 'POST',
    headers,
  })
}

async function proxy() {
  return (await import('@/lib/auth-proxy')).proxyToApi
}

describe('proxyToApi', () => {
  it('forwards the session cookie, so the API can identify the caller', async () => {
    upstream.mockResolvedValue(apiResponse({ ok: true }))
    await (await proxy())(request({ cookie: 'nexus_session=abc' }), {
      path: '/auth/session',
      method: 'GET',
      unavailable: 'down',
    })

    expect(upstream.mock.calls[0][1].headers.get('Cookie')).toBe('nexus_session=abc')
  })

  it('forwards the CSRF header, which is the whole point of having one', async () => {
    upstream.mockResolvedValue(apiResponse({ ok: true }))
    await (await proxy())(request({ 'x-csrf-token': 'a-token' }), {
      path: '/companies',
      method: 'POST',
      body: { name: 'X' },
      unavailable: 'down',
    })

    expect(upstream.mock.calls[0][1].headers.get('X-CSRF-Token')).toBe('a-token')
  })

  it('returns both Set-Cookie headers, not one comma-joined string', async () => {
    // Login sets two cookies. `headers.get('set-cookie')` collapses them into a
    // single comma-joined value that no browser can parse back into two — and
    // splitting on commas is not a fix, because a cookie value may contain one.
    // The symptom is a login that appears to work and has no CSRF cookie.
    upstream.mockResolvedValue(
      apiResponse(
        { user_id: 'u' },
        { cookies: ['nexus_session=a; Path=/; HttpOnly', 'nexus_csrf=b; Path=/'] },
      ),
    )

    const response = await (await proxy())(request(), {
      path: '/auth/login',
      method: 'POST',
      body: {},
      unavailable: 'down',
    })

    const cookies = response.headers.getSetCookie()
    expect(cookies).toHaveLength(2)
    expect(cookies[0]).toContain('nexus_session=a')
    expect(cookies[1]).toContain('nexus_csrf=b')
  })

  it('passes the API status through rather than flattening it', async () => {
    // A 404 that becomes a 500 turns "no dashboard here for you" into "the
    // product is broken", and the UI branches on exactly that distinction.
    upstream.mockResolvedValue(apiResponse({ detail: 'Not found' }, { status: 404 }))

    const response = await (await proxy())(request(), {
      path: '/dashboards/hr',
      method: 'GET',
      unavailable: 'down',
    })

    expect(response.status).toBe(404)
  })

  it('never caches a response', async () => {
    // Every one of these carries workspace data. A cached dashboard is one
    // customer's numbers served to whoever asks next.
    upstream.mockResolvedValue(apiResponse({ ok: true }))

    const response = await (await proxy())(request(), {
      path: '/dashboards',
      method: 'GET',
      unavailable: 'down',
    })

    expect(response.headers.get('cache-control')).toBe('no-store')
  })

  it('turns an unreachable API into 503 with the caller\'s own message', async () => {
    // Not a 500. The API being down is not the same as the API failing, and the
    // UI says something different for each.
    upstream.mockRejectedValue(new Error('ECONNREFUSED'))

    const response = await (await proxy())(request(), {
      path: '/dashboards',
      method: 'GET',
      unavailable: 'Cannot reach the dashboard service right now.',
    })

    expect(response.status).toBe(503)
    expect(await response.json()).toEqual({
      detail: 'Cannot reach the dashboard service right now.',
    })
  })

  it('gives a 204 no body, because a body on a 204 is a protocol error', async () => {
    upstream.mockResolvedValue(apiResponse(null, { status: 204 }))

    const response = await (await proxy())(request(), {
      path: '/auth/logout',
      method: 'POST',
      unavailable: 'down',
    })

    expect(response.status).toBe(204)
    expect(await response.text()).toBe('')
  })

  it('calls a timeout a timeout, not an unreachable service', async () => {
    // **The fix for a message that sent a founder to the wrong diagnosis.**
    //
    // Every failure used to render the caller's `unavailable` sentence. A
    // browser walkthrough hit it while the API was working: one onboarding
    // request spent 37 seconds retrying a rejected question, the 30-second
    // abort fired, and the screen said "Cannot reach the onboarding service
    // right now." The service was reachable the whole time.
    //
    // Different words because different actions: an unreachable service is
    // worth reporting, a slow one is worth retrying.
    upstream.mockRejectedValue(new DOMException('aborted', 'AbortError'))

    const response = await (await proxy())(request(), {
      path: '/onboarding/agent/answer',
      method: 'POST',
      body: {},
      unavailable: 'Cannot reach the onboarding service right now.',
    })

    expect(response.status).toBe(504)
    const body = await response.json()
    expect(body.detail).not.toContain('Cannot reach')
    expect(body.detail).toMatch(/took longer/i)
    expect(body.detail).toMatch(/nothing was lost|nothing is broken/i)
  })

  it('still says unreachable when the service really is unreachable', async () => {
    // The other half. Narrowing the timeout case must not swallow a genuine
    // connection failure into the same reassuring sentence.
    upstream.mockRejectedValue(new TypeError('fetch failed'))

    const response = await (await proxy())(request(), {
      path: '/onboarding/agent/answer',
      method: 'POST',
      body: {},
      unavailable: 'Cannot reach the onboarding service right now.',
    })

    expect(response.status).toBe(503)
    expect((await response.json()).detail).toBe('Cannot reach the onboarding service right now.')
  })

  it('gives every model-backed onboarding route a model-sized timeout', () => {
    // **The guard for the defect a browser found.** Three routes that invoke a
    // skill — brief, answer, tools — were on the thirty-second default, which
    // that constant's own comment says is sized for "a round trip to a managed
    // database". The brief step aborted mid-call while the API was working and
    // the founder was told the service could not be reached.
    //
    // Asserted against the files rather than against a list held here, so a
    // seventh model-backed route cannot be added with the database number and
    // a green suite. The six are the ones whose API handler calls
    // `_require_model()`.
    const modelBacked = ['read', 'brief', 'discovery', 'next', 'answer', 'tools']

    for (const route of modelBacked) {
      const source = readFileSync(
        resolve(__dirname, `../../app/api/onboarding/agent/${route}/route.ts`),
        'utf8',
      )
      const match = source.match(/timeoutMs:\s*([A-Z_0-9]+)/)
      expect(match, `${route} has no timeoutMs and inherits the database default`).toBeTruthy()

      const value = match![1]
      const milliseconds = value === 'MODEL_TIMEOUT_MS' ? MODEL_TIMEOUT_MS : Number(value)
      expect(
        milliseconds,
        `${route} allows ${milliseconds}ms, which is not enough for a model call`,
      ).toBeGreaterThanOrEqual(60_000)
    }
  })
})
