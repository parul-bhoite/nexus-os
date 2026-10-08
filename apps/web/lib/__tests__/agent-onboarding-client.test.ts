import { afterEach, describe, expect, it, vi } from 'vitest'

import { finish } from '@/lib/agent-onboarding-client'

/**
 * `finish()` is single-flighted. The assembly loop awaits each call before the
 * next, so a single well-behaved loop never overlaps itself and these assertions
 * change nothing for it. They pin the one case that was breaking: two loops
 * running at once — a re-invoked effect, or the resumed entry driving assembly
 * alongside the component — where a second, concurrent `finish` landed after the
 * first loop had already reached `ready` and then hung on a database blip,
 * stranding the UI on "Building…" for ever.
 *
 * The contract: concurrent callers share one POST; sequential callers each get a
 * fresh one; and the latch clears whether the request resolves or rejects, so a
 * failure never wedges every call after it.
 */

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

/** The shape `call()` needs: `ok`, `status`, and a `json()` — the rest is cast. */
function okJson(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('finish() single-flight', () => {
  it('coalesces concurrent callers onto one POST and hands them the same result', async () => {
    const pending = deferred<Response>()
    const fetchMock = vi.fn().mockReturnValue(pending.promise)
    vi.stubGlobal('fetch', fetchMock)

    const first = finish()
    const second = finish()

    // The second caller arrived while the first was in flight: no second POST.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/onboarding/agent/finish',
      expect.objectContaining({ method: 'POST' }),
    )

    pending.resolve(okJson({ phase: 'ready', completed: true }))
    const [a, b] = await Promise.all([first, second])

    expect(a).toBe(b)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('issues a fresh POST once the previous one has settled', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson({ phase: 'persona' }))
      .mockResolvedValueOnce(okJson({ phase: 'ready', completed: true }))
    vi.stubGlobal('fetch', fetchMock)

    // Sequential — each advances a stage — so neither coalesces with the other.
    await finish()
    await finish()

    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('clears the latch when the request rejects, so the next call retries', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(okJson({ phase: 'ready', completed: true }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(finish()).rejects.toThrow('network')
    await expect(finish()).resolves.toMatchObject({ phase: 'ready' })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
