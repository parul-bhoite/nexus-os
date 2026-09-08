/**
 * Turning whatever the API returned into a string a person can read.
 *
 * Extracted because the absence of it caused a real crash. `PreviewForm` —
 * since retired with the rest of the pre-signup audit — assigned
 * `payload.detail` straight into a `string` and rendered it. That
 * holds for every error the API raises deliberately — those carry a string —
 * but **FastAPI's own validation errors carry an array of objects**. A URL over
 * the 2048-character limit produced one, React was handed an object as a child,
 * and with no error boundary the whole landing page went white.
 *
 * The lesson is not "add a guard at that call site": it is that `detail` is
 * `unknown` at the boundary and every reader has to treat it that way. This is
 * the one place that does.
 */

/** The first human-readable message in an API error payload, or `fallback`. */
export function messageFrom(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object' || !('detail' in payload)) return fallback

  const detail = (payload as { detail: unknown }).detail

  // The normal case: an error the API raised on purpose, written to be shown.
  if (typeof detail === 'string' && detail.trim() !== '') return detail

  // This API's own structured refusals: `{ error: "skill_failed", message: … }`.
  // Every one of them is written to be read by a person — and every one of them
  // was being thrown away here, because the string branch above does not match
  // an object and the array branch below does not either. The onboarding 502
  // said "The request failed (502)." on screen while the server had sent
  // "The assistant could not produce a usable answer. Nothing was saved."
  //
  // Checked before the array branch for no reason other than that this is now
  // the more common shape; the two cannot both match.
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string' && message.trim() !== '') return message
  }

  // FastAPI request validation: [{ type, loc, msg, input, ctx }, …].
  // The first message is the useful one; the rest repeat it per field.
  if (Array.isArray(detail)) {
    for (const entry of detail) {
      if (entry && typeof entry === 'object') {
        const msg = (entry as { msg?: unknown }).msg
        if (typeof msg === 'string' && msg.trim() !== '') return msg
      }
    }
  }

  return fallback
}
