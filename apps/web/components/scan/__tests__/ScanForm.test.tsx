import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ScanForm } from '@/components/scan/ScanForm'

/**
 * The four states `doc/18` G9 names, plus the fifth it did not: a
 * JavaScript-rendered page (Q51) is not "all held" — both serialise to an
 * empty `checks` array, and only `js_rendered` tells them apart. Found
 * designing the store (G7), carried through to the UI here.
 */

const FINDINGS = {
  id: 'a1b2c3d4-0000-0000-0000-000000000001',
  domain: 'example.om',
  scanned_url: 'https://example.om/',
  pages_read: 1,
  js_rendered: false,
  checks: [
    { id: 'brand.title', label: 'Page title describes the business', evidence: 'no title tag', weight: 15 },
    { id: 'seo.https', label: 'Site is served over HTTPS', evidence: 'served over plain HTTP', weight: 20 },
  ],
  scores: [{ category: 'brand', score: 10, max_score: 70, percentage: 14 }],
  created_at: '2026-09-19T00:00:00Z',
  expires_at: '2026-09-26T00:00:00Z',
}

const ALL_HELD = { ...FINDINGS, checks: [], js_rendered: false }
const JS_RENDERED = { ...FINDINGS, checks: [], js_rendered: true }

function jsonResponse(body: unknown, init: { status?: number; headers?: Record<string, string> } = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })
}

function fillAndSubmit(url = 'https://example.om/') {
  fireEvent.change(screen.getByLabelText(/website address/i), { target: { value: url } })
  fireEvent.click(screen.getByRole('button', { name: /scan my site/i }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ScanForm', () => {
  it('renders the findings state with the calculator\'s own labels and evidence', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(FINDINGS)))
    render(<ScanForm />)

    fillAndSubmit()

    await waitFor(() => expect(screen.getByText('Page title describes the business')).toBeTruthy())
    expect(screen.getByText('no title tag')).toBeTruthy()
    expect(screen.getByText('Site is served over HTTPS')).toBeTruthy()
  })

  it('renders the all-held state, not a blank screen, when nothing failed', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(ALL_HELD)))
    render(<ScanForm />)

    fillAndSubmit()

    await waitFor(() => expect(screen.getByText(/every check held/i)).toBeTruthy())
  })

  it('renders the js-rendered state distinctly from all-held', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(JS_RENDERED)))
    render(<ScanForm />)

    fillAndSubmit()

    await waitFor(() => expect(screen.getByText(/build.*their text in the browser/i)).toBeTruthy())
    expect(screen.queryByText(/every check held/i)).toBeNull()
  })

  it('renders the refused state on a 422', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: 'That address cannot be analysed.' }, { status: 422 })),
    )
    render(<ScanForm />)

    fillAndSubmit()

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('That address cannot be analysed.'))
  })

  it('renders the limited state on a 429, naming when to come back', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(
          { detail: 'Too many scans right now — try again shortly.' },
          { status: 429, headers: { 'Retry-After': '120' } },
        ),
      ),
    )
    render(<ScanForm />)

    fillAndSubmit()

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/try again in about 2 minutes/i))
  })

  it('claims no number the API did not send', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(FINDINGS)))
    render(<ScanForm />)

    fillAndSubmit()

    await waitFor(() => expect(screen.getByText('Page title describes the business')).toBeTruthy())

    // Every numeral rendered in the findings state must trace to the payload:
    // pages_read (1) or a check's own 1-based position in the list. Scoped to
    // the findings container specifically — the shared footer states ADR
    // 0048's fixed 7-day retention policy, which is not a value this
    // component derived from the response.
    const rendered = screen.getByTestId('scan-findings').textContent ?? ''
    const numerals = rendered.match(/\d+/g) ?? []
    const allowed = new Set([String(FINDINGS.pages_read), '1', '2'])
    for (const n of numerals) {
      expect(allowed.has(n)).toBe(true)
    }
    // And the plural is not hard-coded: pages_read === 1 renders "page".
    expect(screen.getByText(/Read 1 page on/)).toBeTruthy()
  })
})
