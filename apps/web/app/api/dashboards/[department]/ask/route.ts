import { NextResponse } from 'next/server'
import { MODEL_TIMEOUT_MS, proxyToApi, readJson } from '@/lib/auth-proxy'
import { DEPARTMENTS } from '@/lib/departments'

export const dynamic = 'force-dynamic'

/**
 * Ask a director a question about the workspace's own documents. `doc/20` A11.
 *
 * **This file is a named artefact in the plan rather than "the web change",
 * because Next.js BFF routes are per path and a missing `route.ts` is a 404
 * neither test suite can see.** The API tests pass, the component tests pass,
 * and the only thing that fails is the product. It has happened in this
 * repository before.
 *
 * `MODEL_TIMEOUT_MS`, for `narrate`'s reason and more so: an ask is an
 * embedding, a vector search, a model call and a ledger write. On the 30-second
 * database default the proxy would abort a request the API is still answering
 * and report that we could not reach a service that was busy working — the
 * skill's own `timeout_seconds` is 45 precisely so the refusal arrives from us,
 * worded, rather than as a gateway error.
 *
 * The department is checked against the same set the sibling routes use. **This
 * is not the security boundary** — `reachable_director` is, and it 404s a
 * department the caller does not hold — it is what keeps an unknown department
 * a 404 here rather than a round trip.
 *
 * A refusal comes back as **200 with `answered: false`**, not as a 4xx. The
 * sentence in it is ours, and an error status would push the client into a path
 * where it invents wording of its own.
 */
export async function POST(
  request: Request,
  { params }: { params: { department: string } },
) {
  if (!DEPARTMENTS.has(params.department)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  const question = typeof body.question === 'string' ? body.question.trim() : ''
  if (!question) {
    return NextResponse.json({ detail: 'Ask a question first.' }, { status: 400 })
  }

  return proxyToApi(request, {
    path: `/dashboards/${params.department}/ask`,
    method: 'POST',
    // One named field, not a spread — this directory's standing rule.
    body: { question },
    timeoutMs: MODEL_TIMEOUT_MS,
    unavailable: 'Cannot reach the assistant right now.',
  })
}
