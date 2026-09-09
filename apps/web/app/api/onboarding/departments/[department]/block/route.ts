import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'
import { DEPARTMENTS } from '@/lib/departments'

export const dynamic = 'force-dynamic'

/**
 * A department's question block — panel 3.
 *
 * The API returns `may_answer` and `binds` rather than leaving a client to
 * infer them, and this route passes them straight through. A UI deciding for
 * itself would be guessing at an authority rule, and the guesses that matter
 * are the wrong ones: a Contributor shown a form that binds, or a Manager shown
 * a read-only block for their own department.
 */
export async function GET(
  request: Request,
  { params }: { params: { department: string } },
) {
  if (!DEPARTMENTS.has(params.department)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/onboarding/departments/${params.department}/block`,
    method: 'GET',
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}

export async function POST(
  request: Request,
  { params }: { params: { department: string } },
) {
  if (!DEPARTMENTS.has(params.department)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/onboarding/departments/${params.department}/block`,
    method: 'POST',
    body: (await readJson(request)) ?? {},
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
