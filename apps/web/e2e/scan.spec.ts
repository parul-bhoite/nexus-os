import { expect, test } from '@playwright/test'

/**
 * `/api/public/scans` and `/api/public/scans/[scanId]`, through the running
 * web app. G8, `doc/18`.
 *
 * **Not `proxyToApi` in isolation.** Next.js App Router resolves a route
 * handler per path segment — a missing `route.ts` is a 404 that neither the
 * Python suite nor a Vitest unit test can see, because one never reaches the
 * web app and the other never makes a request. This uses Playwright's
 * `request` fixture (no browser page needed) to hit the actual dev server's
 * HTTP layer, the same way `e2e/journey.spec.ts` proves the app rather than
 * an imported function.
 *
 * Runs against a real network fetch of a real, IANA-reserved documentation
 * domain (`example.com`) — the point here is proving the routing exists, not
 * re-proving `engine.scan`'s own behaviour, which `test_scan_engine.py`
 * already does against a mocked transport.
 */

test('POST creates a scan and GET reads it back, through the real routes', async ({
  request,
}) => {
  const created = await request.post('/api/public/scans', {
    data: { url: 'https://example.com/' },
  })
  expect([200, 201]).toContain(created.status())
  const body = await created.json()
  expect(body.id).toBeTruthy()
  expect(Array.isArray(body.checks)).toBe(true)

  const read = await request.get(`/api/public/scans/${body.id}`)
  expect(read.status()).toBe(200)
  const readBody = await read.json()
  expect(readBody.id).toBe(body.id)

  const deleted = await request.delete(`/api/public/scans/${body.id}`)
  expect(deleted.status()).toBe(204)

  const afterDelete = await request.get(`/api/public/scans/${body.id}`)
  expect(afterDelete.status()).toBe(404)
})

test('GET on an unknown id is 404, not a routing error', async ({ request }) => {
  const response = await request.get('/api/public/scans/00000000-0000-0000-0000-000000000000')
  expect(response.status()).toBe(404)
})
