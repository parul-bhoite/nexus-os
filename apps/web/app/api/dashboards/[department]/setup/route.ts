import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'
import { DEPARTMENTS } from '@/lib/departments'

export const dynamic = 'force-dynamic'

/**
 * The Setup and Watchlist tabs' content — the founder's own answers, read back.
 *
 * Separate from the director payload on purpose. Finding #23 is that the
 * dashboard already spends 25 to 30 round trips, and most visits to a director
 * page never open Setup; adding a context assembly to every page load would
 * make a known problem worse for content nobody asked for.
 *
 * The gate is upstream and identical to the director page's, in the same order.
 * A lazily-loaded tab is a second door into a department's data, and a caller
 * who gets 404 on the page gets 404 here.
 */
export async function GET(
  request: Request,
  { params }: { params: { department: string } },
) {
  // The same check the sibling route makes, from the same set, before any
  // interpolation.
  if (!DEPARTMENTS.has(params.department)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/dashboards/${params.department}/setup`,
    method: 'GET',
    unavailable: 'Cannot reach the dashboard service right now.',
  })
}
