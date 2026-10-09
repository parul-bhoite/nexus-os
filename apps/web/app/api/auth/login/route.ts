import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/auth/login',
    method: 'POST',
    body: { email: body.email, password: body.password },
    unavailable: 'Sign-in is unavailable right now.',
    // Above the client's 40s ceiling (see `SLOW_DB_TIMEOUT_MS`): the browser
    // owns the deadline, so this leg must not abort a cold-start login first.
    timeoutMs: 45_000,
  })
}
