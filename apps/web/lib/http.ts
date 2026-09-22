import { messageFrom } from '@/lib/api-error'

/**
 * One fetch helper for every browser-side client.
 *
 * Three things every hand-rolled `fetch` in this app kept getting wrong on its
 * own, closed here once:
 *
 * - **No request had a timeout.** `registerCompany`'s ~8s round trip and
 *   `login`'s ~15s one had nothing bounding them — a slow or wedged upstream
 *   left the caller waiting forever with no way to give up (R-02, F-12). Every
 *   call through here carries an `AbortController` with a timeout ceiling,
 *   whether or not the caller supplies its own signal.
 * - **`!response.ok` was sometimes never checked.** `deleteScan` fired and
 *   forgot; `documents-client`'s `uploadDocument` on-purpose 422 branch used
 *   to be gated on nothing but the status code (F-10, F-16 below). This throws
 *   `HttpError` — with the canonical `messageFrom` — on every non-2xx unless
 *   the caller explicitly opts out.
 * - **An OK response with an empty or unparseable body reached the caller as
 *   `null`, un-checked.** `dashboard-client.ts`'s `get()` did
 *   `await response.json().catch(() => null)` and returned it regardless — a
 *   silent `null` surfacing as a crash three renders later (F-03). This
 *   throws instead, at the boundary, where the actual failure happened.
 */

export class HttpError extends Error {
  readonly status: number
  readonly detail: unknown
  constructor(message: string, status: number, detail?: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

/** Generous, but not infinite — long enough for the slowest ordinary call
 *  (`registerCompany` against Neon, ~8s) with headroom, short enough that a
 *  wedged upstream is eventually reported rather than waited on forever. */
const DEFAULT_TIMEOUT_MS = 20_000

export type HttpOptions = RequestInit & {
  /** Overrides `DEFAULT_TIMEOUT_MS` for a call known to run long or short. */
  timeoutMs?: number
  /** What to say for a non-2xx with no readable `detail`. */
  fallbackMessage?: string
  /** Treat 2xx with no body as `null` rather than throwing — for a `DELETE`
   *  or similar that is expected to answer 204. Off by default: an *unexpected*
   *  empty body is exactly the bug F-03 and F-10 both were. */
  allowEmptyBody?: boolean
  /**
   * Called with the raw `Response`, before its body is read.
   *
   * The one thing `httpJson`'s own return value cannot carry is a response
   * header — `scan-client.ts`'s `startScan` needs `Retry-After` off a 429,
   * which is otherwise gone the moment this function has parsed the body and
   * thrown. An escape hatch rather than widening `HttpError` with a `headers`
   * field every other caller would then carry and never read.
   */
  onResponse?: (response: Response) => void
}

/**
 * `fetch`, with a timeout ceiling, a checked status and a checked body.
 *
 * `T` is `void` for a call that expects no body (pass `allowEmptyBody: true`);
 * otherwise a non-2xx or an empty 2xx both throw `HttpError` rather than
 * handing the caller something to forget to check.
 */
export async function httpJson<T>(path: string, options: HttpOptions = {}): Promise<T> {
  const {
    timeoutMs = DEFAULT_TIMEOUT_MS,
    fallbackMessage,
    allowEmptyBody = false,
    onResponse,
    signal: callerSignal,
    ...init
  } = options

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  const onExternalAbort = () => controller.abort()
  if (callerSignal) callerSignal.addEventListener('abort', onExternalAbort)

  let response: Response
  try {
    response = await fetch(path, { ...init, signal: controller.signal })
  } catch (error) {
    if (controller.signal.aborted) {
      // Distinguishing "we gave up" from "the caller cancelled" is not
      // possible from the outside — both are `AbortError` — so this reads as
      // a timeout, which is the more common cause and the more actionable
      // message either way.
      throw new HttpError('That took too long. Try again.', 0)
    }
    throw error
  } finally {
    clearTimeout(timeout)
    if (callerSignal) callerSignal.removeEventListener('abort', onExternalAbort)
  }

  onResponse?.(response)

  if (response.status === 204) {
    if (allowEmptyBody) return null as T
    throw new HttpError('The server did not return anything usable.', response.status)
  }

  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    throw new HttpError(
      messageFrom(payload, fallbackMessage ?? `The request failed (${response.status}).`),
      response.status,
      (payload as { detail?: unknown } | null)?.detail,
    )
  }

  if (payload === null && !allowEmptyBody) {
    throw new HttpError('The server did not return anything usable.', response.status)
  }

  return payload as T
}
