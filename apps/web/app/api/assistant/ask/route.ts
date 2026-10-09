import { NextResponse } from 'next/server'
import { MODEL_TIMEOUT_MS, proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Ask the global, metric-aware assistant (ADR 0086). The company-wide
 * counterpart to the per-department `.../ask` route: this one answers from the
 * workspace's own figures, insights and facts rather than its documents.
 *
 * A named artefact for the per-path reason the per-department route gives — a
 * missing `route.ts` is a 404 no test suite sees. `MODEL_TIMEOUT_MS` because an
 * ask is a model call plus a ledger write, well past the database default.
 *
 * The API 404s while the feature is dark (the A12 flag off); this route forwards
 * that unchanged. A refusal comes back as **200 with `answered: false`** and a
 * sentence the API wrote — an error status would push the client to invent its
 * own wording.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  const question = typeof body.question === 'string' ? body.question.trim() : ''
  if (!question) {
    return NextResponse.json({ detail: 'Ask a question first.' }, { status: 400 })
  }

  return proxyToApi(request, {
    path: '/assistant/ask',
    method: 'POST',
    // One named field, not a spread — this directory's standing rule.
    body: { question },
    timeoutMs: MODEL_TIMEOUT_MS,
    unavailable: 'Cannot reach the assistant right now.',
  })
}
