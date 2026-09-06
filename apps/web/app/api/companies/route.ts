import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Registers a company.
 *
 * Named fields, not a spread — the same rule the register proxy states. Note
 * `confirm_separate_company` in particular: it is the deliberate override for
 * "a company already holds this domain", and forwarding it by accident from an
 * arbitrary body would turn a confirmation into a default.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/companies',
    method: 'POST',
    body: {
      name: body.name,
      website_url: body.website_url,
      // Presentation only, and forwarded by name like everything else here.
      // Left out of this list they are dropped silently: the form collects
      // them, the API accepts them, and the column stays null with nothing
      // anywhere saying why. That is the cost of the allowlist and the reason
      // it is worth it — the same rule stops `confirm_separate_company`
      // arriving by accident.
      designation: body.designation ?? null,
      department: body.department ?? null,
      confirm_separate_company: body.confirm_separate_company === true,
    },
    unavailable: 'Cannot reach the account service right now.',
  })
}
