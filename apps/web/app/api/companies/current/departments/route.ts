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
    // Not a model route, but not a single-statement read either: replacing the
    // department set is a delete-and-reinsert that re-derives what each director
    // can see, and against a managed database that can run past the 30s default.
    // When it did, the abort left the write holding a lock, so the retry timed
    // out too — a founder stuck mid-onboarding on a 504 (ADR 0069 verification).
    // 90s is comfortably above the slow-day write and still well below a hang.
    // An explicit literal, not MODEL_TIMEOUT_MS: no model is called here, and
    // `auth-proxy.test.ts` reserves that constant for routes that invoke a skill.
    timeoutMs: 90_000,
  })
}
