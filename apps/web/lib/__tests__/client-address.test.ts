import { describe, expect, it } from 'vitest'
import { clientAddress } from '@/lib/client-address'

/**
 * `clientAddress` had no test at all when it was first written (`8fedbb1`) —
 * the audit that found the per-IP rate limit completely bypassable
 * (AUDIT-FINDINGS.md) landed the fix with zero coverage of its own. Restored
 * for G6 with the gap closed this time: the one property this function
 * exists for is that a browser-supplied header can never reach its return
 * value, and that is exactly what these assert.
 *
 * L-03: `x-real-ip` was once trusted as a fallback for `request.ip`, on the
 * reasoning that a reverse proxy sets it and a browser cannot. That reasoning
 * does not hold for *this* deployment: `x-real-ip` is an ordinary request
 * header, and unless the specific edge in front of this app is known to
 * strip or overwrite it on every hop — never verified — a client can set it
 * to anything, which is the identical bypass this file exists to close for
 * `x-forwarded-for`. `request.ip`, set by the hosting platform from the
 * actual TCP peer, is the only source these tests treat as trustworthy.
 */

function requestWith(opts: { ip?: string; realIp?: string; forwardedFor?: string }): Request {
  const headers = new Headers()
  if (opts.realIp) headers.set('x-real-ip', opts.realIp)
  // A browser cannot set `x-real-ip` through any sane proxy configuration,
  // but it can send whatever it likes as `x-forwarded-for` — included here to
  // prove that header is never read at all, not merely deprioritised.
  if (opts.forwardedFor) headers.set('x-forwarded-for', opts.forwardedFor)

  const request = new Request('https://nexus-os.example/api/public/scans', { headers })
  if (opts.ip) {
    Object.defineProperty(request, 'ip', { value: opts.ip })
  }
  return request
}

describe('clientAddress', () => {
  it('prefers the platform-set request.ip', () => {
    const request = requestWith({ ip: '203.0.113.9', realIp: '198.51.100.1' })
    expect(clientAddress(request)).toEqual({ 'X-Forwarded-For': '203.0.113.9' })
  })

  // L-03: `x-real-ip` is no longer a trusted fallback — see the file's top
  // note. Absent `request.ip`, this now omits the header entirely rather
  // than trusting a header a client can set.
  it('does not fall back to x-real-ip when request.ip is absent', () => {
    const request = requestWith({ realIp: '198.51.100.1' })
    expect(clientAddress(request)).toEqual({})
  })

  it('omits the header entirely when neither is available', () => {
    const request = requestWith({})
    expect(clientAddress(request)).toEqual({})
  })

  it('never reads a browser-supplied x-forwarded-for or x-real-ip, with or without request.ip present', () => {
    const spoofed = requestWith({ forwardedFor: '1.2.3.4' })
    expect(clientAddress(spoofed)).toEqual({})

    // L-03: a spoofed `x-real-ip` must be ignored too, not merely
    // deprioritised behind `x-forwarded-for` — `request.ip` is the only
    // source trusted, and its absence here means no header at all.
    const spoofedRealIp = requestWith({ realIp: '198.51.100.1', forwardedFor: '1.2.3.4' })
    expect(clientAddress(spoofedRealIp)).toEqual({})

    const withRealIp = requestWith({ ip: '203.0.113.9', realIp: '198.51.100.1', forwardedFor: '1.2.3.4' })
    expect(clientAddress(withRealIp)).toEqual({ 'X-Forwarded-For': '203.0.113.9' })
  })

  it('varying the spoofed header across requests still produces no address', () => {
    // The defect this restores a fix for: a bypassable per-IP limit lets one
    // caller change X-Forwarded-For on every request and land in a fresh
    // bucket each time. Two different spoofed values must both be ignored.
    expect(clientAddress(requestWith({ forwardedFor: '1.2.3.4' }))).toEqual({})
    expect(clientAddress(requestWith({ forwardedFor: '5.6.7.8' }))).toEqual({})
  })
})
