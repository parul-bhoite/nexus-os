/**
 * The visitor's address, from headers the *platform* sets — never from the
 * request the browser sent.
 *
 * The API trusts `X-Forwarded-For` when the direct peer is a configured trusted
 * proxy, which this app is. Forwarding the browser's own copy of that header
 * therefore hands every visitor the ability to choose their own rate-limit
 * bucket: send `X-Forwarded-For: 1.2.3.4`, change it each request, and the
 * per-IP limit stops existing.
 *
 * **Only `request.ip`, set by the hosting platform from the actual TCP peer, is
 * used.** `x-real-ip` used to be an accepted fallback, and that was the same
 * mistake `X-Forwarded-For` makes: it is an ordinary request header, and unless
 * this deployment's edge is known to overwrite it on every hop (verified, not
 * assumed) a client can set it to anything. L-03 — a spoofable header client
 * code trusted the platform to have already stripped is worse than no address
 * at all, because it reads as trustworthy. If `request.ip` is unavailable the
 * header is omitted entirely and the API falls back to its direct peer — one
 * shared bucket for everyone, which is a worse limit but a safe one.
 *
 * Restored for the anonymous Instant Gap Analysis scanner (ADR 0046, `doc/18`
 * G6) — deleted with the rest of the retired preview audit at `dc287dd` (P2),
 * unchanged here because the trust problem it solves is identical.
 */
export function clientAddress(request: Request): Record<string, string> {
  // `NextRequest.ip` where the platform provides it. This is the one source
  // that cannot be spoofed by a browser — it is derived from the TCP
  // connection itself, not from a header the client can set.
  const direct = (request as Request & { ip?: string }).ip
  if (direct) return { 'X-Forwarded-For': direct }

  return {}
}
