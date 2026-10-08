import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Edit one price row (ADR 0076/0077). `kind`/`key` come from the path; the body
 * is narrowed to `amount_minor` + `active` before forwarding so a malformed
 * payload fails the API's own validation rather than passing through unchecked.
 * Platform-admin only — enforced by the API on the caller's email.
 */
export async function PUT(
  request: Request,
  { params }: { params: Promise<{ kind: string; key: string }> },
) {
  const { kind, key } = await params
  const body = await readJson(request)
  const amount = Number((body as Record<string, unknown>)?.amount_minor)
  const active = (body as Record<string, unknown>)?.active

  return proxyToApi(request, {
    path: `/admin/prices/${encodeURIComponent(kind)}/${encodeURIComponent(key)}`,
    method: 'PUT',
    body: {
      amount_minor: Number.isFinite(amount) ? Math.round(amount) : 0,
      active: active === true,
    },
    unavailable: 'Cannot reach the billing service right now.',
  })
}
