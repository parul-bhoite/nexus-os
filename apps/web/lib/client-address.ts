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
 * `request.ip` (set by the hosting platform) and `x-real-ip` (set by the
 * reverse proxy, not forwarded from the client by any sane configuration) are
 * the two that cannot be spoofed by a browser. If neither is available the
 * header is omitted entirely and the API falls back to its direct peer — one
 * shared bucket for everyone, which is a worse limit but a safe one.
 *
 * Restored for the anonymous Instant Gap Analysis scanner (ADR 0046, `doc/18`
 * G6) — deleted with the rest of the retired preview audit at `dc287dd` (P2),
 * unchanged here because the trust problem it solves is identical.
 */
export function clientAddress(request: Request): Record<string, string> {
  // `NextRequest.ip` where the platform provides it.
  const direct = (request as Request & { ip?: string }).ip
  if (direct) return { 'X-Forwarded-For': direct }

  const real = request.headers.get('x-real-ip')
  if (real) return { 'X-Forwarded-For': real }

  return {}
}
