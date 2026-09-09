import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The Company Brain — panel 10, read-only.
 *
 * `provenance` and `assumptions` come back with it because a brain the founder
 * cannot audit is a brain they have to take on trust, and this product's whole
 * claim is that they never have to.
 *
 * There is no DELETE here. Removing an item has to fan out to its passages, its
 * embeddings, cached answers and derivations, and that fan-out is P21's — a
 * delete button that removed the row and left the embeddings would leave the
 * fact retrievable by the one path that matters.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/brain',
    method: 'GET',
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
