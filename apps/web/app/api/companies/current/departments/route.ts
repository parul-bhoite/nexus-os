import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Which departments the company runs — panel 7.
 *
 * **Not the onboarding route.** `POST /onboarding/departments` calls
 * `complete_stage`, so pointing this at it would re-advance a finished spine
 * every time somebody changed their mind in Settings, and the change would read
 * as onboarding progress in the audit trail.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/companies/current/departments',
    method: 'GET',
    unavailable: 'Cannot reach the account service right now.',
  })
}

export async function PUT(request: Request) {
  return proxyToApi(request, {
    path: '/companies/current/departments',
    method: 'PUT',
    body: (await readJson(request)) ?? {},
    unavailable: 'Cannot reach the account service right now.',
  })
}
