import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BlockCard } from '@/components/dashboard/BlockCard'
import type { DirectorBlock, NarrationResult } from '@/lib/dashboard-client'

/**
 * The sentence on a tile: where it sits, what asks for it, and what happens
 * when there is none.
 *
 * Separate from `BlockCard.test.tsx` because that file is deliberately driven
 * by props alone and these need `fetch`. The split is worth keeping: a state
 * matrix that suddenly needs a network double is a state matrix people stop
 * extending.
 *
 * **Position is asserted, not just presence.** `BlockCard`'s own docstring
 * argues the ordering — figure, then sentence, then "needs keyword data" —
 * because a gloss on the number belongs on the number's side of that line, and
 * below the consequence it reads as a footnote to a footnote. Nothing but a DOM
 * order assertion can catch that being lost in a refactor; every
 * `getByText` passes with the paragraphs in any order at all.
 */

const NARRATION = {
  prose: 'Most of the nine checks pass; the page has no internal links.',
  narrated_at: '2026-09-16T10:00:00Z',
  prompt_version: '1',
}

function figure(overrides: Record<string, unknown> = {}) {
  return {
    label: 'Technical SEO',
    measures: 'Nine checks on the one page we fetched.',
    score: 45,
    max_score: 65,
    percentage: 69,
    checks: [
      { id: 'seo.https', label: 'Served over HTTPS', passed: true, weight: 10, evidence: 'https' },
    ],
    checks_passed: 6,
    source_url: 'https://muscat-marine.om/',
    measured_at: '2026-09-09',
    method: 'calculators.audit.score_technical_seo',
    ...overrides,
  }
}

function block(overrides: Partial<DirectorBlock> = {}): DirectorBlock {
  return {
    key: 'marketing.seo_gaps',
    doc05_id: '3.7',
    name: 'SEO Intelligence',
    shows: 'Technical SEO score',
    block: 'metric',
    state: 'partial',
    unlock: 'Needs keyword data.',
    needs: ['keywords'],
    figure: figure(),
    ...overrides,
  }
}

function answered(overrides: Partial<NarrationResult> = {}): NarrationResult {
  return {
    key: 'marketing.seo_gaps',
    outcome: 'answered',
    reason: '',
    message: '',
    narration: NARRATION,
    generation_id: 'gen-1',
    measured_at: '2026-09-09',
    tokens_left_today: 9000,
    ...overrides,
  }
}

function refused(reason: string, message: string): NarrationResult {
  return {
    key: 'marketing.seo_gaps',
    outcome: 'unavailable',
    reason,
    message,
    narration: null,
    generation_id: 'gen-2',
    measured_at: '2026-09-09',
    tokens_left_today: 0,
  }
}

function respond(result: NarrationResult) {
  return vi.fn(async () => new Response(JSON.stringify(result), { status: 200 }))
}

beforeEach(() => {
  vi.stubGlobal('fetch', respond(answered()))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the button that asks for a sentence', () => {
  it('offers to explain a figure, and does not offer on a tile with none', () => {
    const { unmount } = render(<BlockCard block={block()} department="marketing" />)
    expect(screen.getByRole('button', { name: 'Explain this score' })).toBeTruthy()
    unmount()

    // No figure means nothing to explain, and a button that asks a model to
    // describe a number nobody computed is the one thing this must not offer.
    render(<BlockCard block={block({ state: 'locked', figure: null })} department="marketing" />)
    expect(screen.queryByRole('button', { name: 'Explain this score' })).toBeNull()
  })

  it('never fetches on render — a page load must not spend the allowance', async () => {
    // Seven directors' worth of tiles narrating themselves on arrival would
    // exhaust a founder's daily tokens on figures nobody looked at.
    render(<BlockCard block={block()} department="marketing" />)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('posts the capability id it was served, to its own department', async () => {
    render(<BlockCard block={block()} department="marketing" />)
    fireEvent.click(screen.getByRole('button', { name: 'Explain this score' }))

    await waitFor(() => expect(fetch).toHaveBeenCalled())
    const [url, init] = (fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock
      .calls[0]
    expect(url).toBe('/api/dashboards/marketing/narrate')
    expect(init.method).toBe('POST')
    // The key travels whole. Composing it from a department plus a block name
    // would be a second spelling of one thing, and the API refuses a key that
    // does not belong to the department in the path.
    expect(JSON.parse(String(init.body))).toEqual({ key: 'marketing.seo_gaps' })
  })

  it('shows the sentence, and then offers to write another one quietly', async () => {
    render(<BlockCard block={block()} department="marketing" />)
    fireEvent.click(screen.getByRole('button', { name: 'Explain this score' }))

    expect(await screen.findByText(NARRATION.prose)).toBeTruthy()
    // "Explain again", not "Explain this score" a second time: re-narrating
    // spends tokens and must not read as the tile's main control.
    expect(screen.getByRole('button', { name: 'Explain again' })).toBeTruthy()
  })
})

describe('where the sentence sits', () => {
  it('renders between the figure and the consequence', () => {
    const { container } = render(
      <BlockCard block={block({ narration: NARRATION })} department="marketing" />,
    )

    const text = Array.from(container.querySelectorAll('p, a')).map((node) => node.textContent ?? '')
    const score = text.findIndex((line) => line.includes('45'))
    const prose = text.findIndex((line) => line.includes(NARRATION.prose))
    const consequence = text.findIndex((line) => line.includes('Needs keyword data.'))

    expect(score).toBeGreaterThanOrEqual(0)
    expect(prose).toBeGreaterThan(score)
    expect(consequence).toBeGreaterThan(prose)
  })

  it('shows a stored sentence on arrival without being asked', () => {
    // The whole point of storing it. A narration that had to be re-requested on
    // every page load would be a cache that charges for its own misses.
    render(<BlockCard block={block({ narration: NARRATION })} department="marketing" />)
    expect(screen.getByText(NARRATION.prose)).toBeTruthy()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('names the skill that wrote it, in the working drawer', async () => {
    render(<BlockCard block={block({ narration: NARRATION })} department="marketing" />)
    fireEvent.click(screen.getByRole('button', { name: '+ why this number' }))

    // Beside the calculator's method. A disputed sentence should trace to its
    // instructions as readily as a disputed figure traces to its arithmetic.
    expect(screen.getByText(/narrate-metric 1/)).toBeTruthy()
  })
})

describe('refusals, which are answers rather than errors', () => {
  it('renders the server’s own words and hides the button when retrying is pointless', async () => {
    const message =
      'This deployment has no language model configured. The score is unaffected.'
    vi.stubGlobal('fetch', respond(refused('model_unavailable', message)))

    render(<BlockCard block={block()} department="marketing" />)
    fireEvent.click(screen.getByRole('button', { name: 'Explain this score' }))

    expect(await screen.findByText(message)).toBeTruthy()
    // Hidden, not disabled. A disabled button reads as broken; an absent one
    // beside an unchanged score reads as "this deployment does not do that",
    // which is what ADR 0011 says a missing key actually is.
    expect(screen.queryByRole('button', { name: /Explain|Try again/ })).toBeNull()
  })

  it('offers another attempt when the refusal is one a retry could clear', async () => {
    vi.stubGlobal(
      'fetch',
      respond(refused('invented_number', 'The explanation stated a figure nothing computed.')),
    )

    render(<BlockCard block={block()} department="marketing" />)
    fireEvent.click(screen.getByRole('button', { name: 'Explain this score' }))

    // `invented_number` is the guard working, not the product failing, and a
    // second attempt usually succeeds.
    expect(await screen.findByRole('button', { name: 'Try again' })).toBeTruthy()
  })

  it('refuses to show a sentence about a figure the reader cannot see', async () => {
    // Re-crawled between load and click: the prose is true about a score that
    // is no longer on screen, and rendering it beside the old one is the single
    // way this feature can state something false.
    vi.stubGlobal('fetch', respond(answered({ measured_at: '2026-09-16' })))

    render(<BlockCard block={block()} department="marketing" />)
    fireEvent.click(screen.getByRole('button', { name: 'Explain this score' }))

    expect(
      await screen.findByText('This score has changed since the page loaded. Reload to see it.'),
    ).toBeTruthy()
    expect(screen.queryByText(NARRATION.prose)).toBeNull()
  })

  it('keeps the number checkable while it is writing', async () => {
    let release: (value: Response) => void = () => {}
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>((resolve) => (release = resolve))),
    )

    render(<BlockCard block={block()} department="marketing" />)
    fireEvent.click(screen.getByRole('button', { name: 'Explain this score' }))

    const button = await screen.findByRole('button', { name: 'Writing…' })
    expect(button.getAttribute('aria-busy')).toBe('true')
    // The drawer and the source link stay live: the figure is on screen and
    // stays checkable while a sentence about it is being written.
    expect(screen.getByRole('button', { name: '+ why this number' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'https://muscat-marine.om/' })).toBeTruthy()

    release(new Response(JSON.stringify(answered()), { status: 200 }))
    expect(await screen.findByText(NARRATION.prose)).toBeTruthy()
  })
})
