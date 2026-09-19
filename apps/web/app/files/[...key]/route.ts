import { proxyDownload } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The path a signed URL actually points at.
 *
 * `FilesystemObjectStore.signed_url` mints `/files/{key}?expires=…&sig=…` with
 * a **relative** base, so a browser given that link asks *this* app for it, not
 * the API. Until this route existed, every signed URL in the product resolved
 * to a 404 on this origin — the same shape of gap the API itself had before
 * `routes/files.py` was written, one hop further out.
 *
 * A catch-all segment because a storage key has slashes in it: keys are
 * `{workspace}/{document}`-shaped, and `[key]` would match only the first
 * segment and 404 the rest.
 *
 * **The query string is forwarded, and it is the credential.** `expires` and
 * `sig` are what the API verifies; dropping them would turn every download into
 * a refusal, and rewriting them is not something this hop is entitled to do.
 * Nothing here inspects or re-signs them.
 */
export async function GET(request: Request, { params }: { params: { key: string[] } }) {
  const key = params.key.map(encodeURIComponent).join('/')
  const query = new URL(request.url).search

  return proxyDownload(request, {
    path: `/files/${key}${query}`,
    unavailable: 'Cannot reach the file service right now.',
  })
}
