import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The common surface's own payload.
 *
 * Separate from `/api/dashboards`, which the shell fetches on every signed-in
 * page to draw its navigation. Folding the brief into that response would
 * compute an audit for somebody sitting in Settings, so this is fetched only by
 * the Today page.
 *
 * The default timeout is the right one: nothing here reaches a model. The brief
 * is computed in code (ADR 0029) precisely so it cannot refuse, cannot bill,
 * and cannot hang waiting on a provider — which is also why this route needs
 * none of `narrate`'s longer window.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/dashboards/surface',
    method: 'GET',
    unavailable: 'Cannot reach the dashboard service right now.',
  })
}
