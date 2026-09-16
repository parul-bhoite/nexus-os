import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MorningBrief } from '@/components/dashboard/MorningBrief'
import type { Brief, BriefItem } from '@/lib/dashboard-client'

/**
 * The brief on screen. ADR 0029.
 *
 * Almost every rule it obeys is enforced server-side in `domain/brief.py`, and
 * that is deliberate — a browser that re-sorted or re-worded would be a second
 * opinion about the same data. What is left for this file is what only the
 * screen can get wrong:
 *
 * - **The region is never absent.** Three states, three renderings; a brief that
 *   returned `null` for "nothing measured" would let an audit that never ran
 *   look like one that found nothing (I10).
 * - **The two tiers follow the weights**, not a fixed count — the cut has to
 *   move when the data does.
 * - **A collapsed item still says what it is.** The first cut showed only the
 *   evidence, and "137 characters" identifies nothing on its own.
 */

function item(overrides: Partial<BriefItem> = {}): BriefItem {
  return {
    kind: 'check_failed',
    headline: 'Served over HTTPS',
    detail: 'http only',
    cost: 10,
    check_id: 'seo.https',
    capability_id: 'marketing.seo_gaps',
    method: 'calculators.audit.score_technical_seo',
    ...overrides,
  }
}

function brief(overrides: Partial<Brief> = {}): Brief {
  return {
    state: 'findings',
    items: [
      item(),
      item({ headline: 'Meta description is a usable length', check_id: 'seo.description' }),
      item({ headline: 'Structured data is present', detail: 'no JSON-LD', cost: 5, check_id: 'seo.structured_data' }),
      item({ headline: 'Page language is declared', detail: 'no lang attribute', cost: 5, check_id: 'seo.language' }),
    ],
    message: '8 of 18 checks did not hold.',
    points_held: 85,
    points_total: 135,
    checks_passed: 10,
    checks_total: 18,
    measured_on: '2026-09-16',
    ...overrides,
  }
}

describe('the three states all render something', () => {
  it('lists findings, with what each cost', () => {
    render(<MorningBrief brief={brief()} />)

    expect(screen.getByText(/8 of 18 checks did not hold/)).toBeTruthy()
    expect(screen.getByText(/50 of 135 points not held/)).toBeTruthy()
    expect(screen.getByText('Served over HTTPS')).toBeTruthy()
  })

  it('states full marks and the server’s limits sentence in the same card', () => {
    const message =
      'Every check held. That is not a clean bill of health: the audit reads one page.'
    render(
      <MorningBrief
        brief={brief({ state: 'all_held', items: [], message, points_held: 135, checks_passed: 18 })}
      />,
    )

    expect(screen.getByText(/All 18 checks held/)).toBeTruthy()
    // The wording is the API's. A map from state to sentence in the browser is
    // the failure `unlock` already avoids.
    expect(screen.getByText(message)).toBeTruthy()
  })

  it('renders "nothing measured" as its own statement, never as an empty findings list', () => {
    const message = 'No page has been fetched — which is not the same as nothing being wrong.'
    const { container } = render(
      <MorningBrief
        brief={brief({
          state: 'not_measured',
          items: [],
          message,
          points_held: 0,
          points_total: 0,
          checks_passed: 0,
          checks_total: 0,
          measured_on: '',
        })}
      />,
    )

    expect(screen.getByText(/Nothing measured yet/)).toBeTruthy()
    expect(screen.getByText(message)).toBeTruthy()
    // I10, asserted as an absence of a number rather than as the presence of a
    // word: a zero score here is the exact substitution the invariant forbids.
    expect(container.textContent).not.toMatch(/0 of 0/)
    expect(container.querySelector('section')).toBeTruthy()
  })
})

describe('the two tiers', () => {
  it('gives full items to the heaviest band and collapses the rest', () => {
    render(<MorningBrief brief={brief()} />)

    // Two at ten points lead; the two fives collapse.
    expect(screen.getByText(/2 more checks did not hold/)).toBeTruthy()
    expect(screen.getByText('Served over HTTPS')).toBeTruthy()
  })

  it('moves the cut when the weights move, rather than keeping a fixed count', () => {
    // Everything at one weight: nothing is collapsed, because there is no
    // second tier in the data.
    render(<MorningBrief brief={brief({ items: [item(), item({ check_id: 'b' })] })} />)

    expect(screen.queryByText(/more checks did not hold/)).toBeNull()
  })

  it('keeps the check name on a collapsed item', () => {
    const { container } = render(<MorningBrief brief={brief()} />)
    const collapsed = container.querySelectorAll('li')
    const text = Array.from(collapsed).map((node) => node.textContent ?? '')

    // "no lang attribute" on its own identifies nothing; the label is the half
    // that says what was being counted.
    expect(text.some((line) => line.includes('Page language is declared') && line.includes('no lang attribute'))).toBe(true)
  })
})

describe('provenance and restraint', () => {
  it('names the check and the calculator behind every full item', () => {
    render(<MorningBrief brief={brief()} />)

    expect(
      screen.getAllByText(/seo\.https · calculators\.audit\.score_technical_seo/).length,
    ).toBeGreaterThan(0)
  })

  it('shows an unmeasured capability without inventing a cost for it', () => {
    const unmeasured = item({
      kind: 'unmeasured',
      headline: 'This could not be measured',
      detail: 'Nothing scored it on the most recent fetch.',
      cost: 0,
      check_id: '',
      method: '',
      capability_id: 'marketing.brand_intelligence',
    })
    render(<MorningBrief brief={brief({ items: [unmeasured, ...brief().items] })} />)

    const entry = screen.getByText('This could not be measured').closest('li')
    expect(entry).toBeTruthy()
    // No points badge: nothing was scored, so a number would be manufactured.
    expect(within(entry as HTMLElement).queryByText(/point/)).toBeNull()
    expect(within(entry as HTMLElement).getByText(/marketing\.brand_intelligence/)).toBeTruthy()
  })
})
