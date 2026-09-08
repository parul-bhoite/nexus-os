import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Three named documents per department this company runs, and the limits.
 *
 * Named beats generic — "upload some documents" gets nothing, "your current
 * price list" gets a file — so the asks come from the server, where they are
 * chosen from the department selection rather than guessed at by the screen.
 *
 * The consent warranty comes with them, and it is the wording the upload is
 * recorded against. The browser must render the text the API sent rather than
 * its own copy of it: what a customer consented to is a question about the words
 * in force at the time, and a second copy in TypeScript would be a second
 * answer.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/documents/asks',
    method: 'GET',
    unavailable: 'Cannot reach the document service right now.',
  })
}
