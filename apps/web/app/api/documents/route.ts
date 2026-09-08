import { proxyToApi, proxyUpload } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Upload a document, and list the ones already uploaded.
 *
 * `POST` goes through `proxyUpload` rather than `proxyToApi`, which is not a
 * detail: `proxyToApi` JSON-stringifies its body, which turns a file into the
 * string `[object Object]` and destroys the multipart boundary. The body
 * streams through untouched so the API's own parser sees exactly what the
 * browser sent — including the `consent` form field, which the API refuses the
 * upload without.
 *
 * The status codes are forwarded as they are, and three of them are meaningful:
 * 201 for a document that was indexed, **422 for one that was stored but could
 * not be parsed**, and 413 over a limit. A client that only checked for 2xx
 * would report a scanned PDF with no text layer as searchable — which is
 * finding F11, and is the reason the API stopped calling that case Created.
 */
export async function POST(request: Request) {
  return proxyUpload(request, {
    path: '/documents',
    unavailable: 'Cannot reach the document service right now.',
  })
}

export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/documents',
    method: 'GET',
    unavailable: 'Cannot reach the document service right now.',
  })
}
