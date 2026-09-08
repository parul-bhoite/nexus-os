import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  // Fields are named, not spread. Spreading would forward anything the caller
  // invented; naming them means this list is the contract.
  //
  // `display_name` and `phone` are on it because the form now asks for both —
  // the name so the agent can address the person for the rest of onboarding.
  // Until they were added here the form collected them, the client sent them
  // and the API accepted them, and both columns stayed null with nothing
  // anywhere reporting a problem. That is the allowlist's cost, and it is worth
  // paying: the alternative forwards whatever a caller invents.
  return proxyToApi(request, {
    path: '/auth/register',
    method: 'POST',
    body: {
      email: body.email,
      password: body.password,
      display_name: body.display_name ?? null,
      phone: body.phone ?? null,
    },
    unavailable: 'Accounts are unavailable right now.',
  })
}
