import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BlockCard } from '@/components/dashboard/BlockCard'
import {
  STATE_LABEL,
  type BlockKind,
  type DirectorBlock,
  type WidgetState,
} from '@/lib/dashboard-client'

/**
 * Every state, and every block kind. `doc/13` §7 and §6.
 *
 * The rule the whole thing serves: **each state has to tell the reader
 * something different to do.** Two states that produce the same action should
 * be one state, and a state whose action is wrong is worse than no tile at all.
 * So these tests assert on the *copy*, because the copy is the behaviour.
 *
 * Driven with props rather than through the API on purpose. Nothing is
 * reachable yet, so every real block is `planned` — and a component whose other
 * seven states are unreachable in practice is a component nobody has checked.
 */

const ALL_STATES: WidgetState[] = [
  'live',
  'partial',
  'locked',
  'warming',
  'self_reported',
  'stale',
  'unavailable',
  'planned',
]

const ALL_KINDS: BlockKind[] = [
  'metric',
  'trend',
  'table',
  'board',
  'cards',
  'queue',
  'facts',
  'panel',
  'studio',
]

function figure(overrides: Partial<NonNullable<DirectorBlock['figure']>> = {}) {
  return {
    label: 'Technical SEO',
    measures:
      'Nine checks on the one page we fetched. Not keyword volumes, difficulty or rankings.',
    score: 45,
    max_score: 65,
    percentage: 69,
    checks: [
      {
        id: 'seo.https',
        label: 'Served over HTTPS',
        passed: true,
        weight: 10,
        evidence: 'https',
      },
      {
        id: 'seo.internal_links',
        label: 'Links to its own pages',
        passed: false,
        weight: 5,
        evidence: '0 internal links',
      },
    ],
    checks_passed: 7,
    source_url: 'https://muscat-marine.om/',
    measured_at: '2026-09-09',
    method: 'calculators.audit.score_technical_seo',
    ...overrides,
  }
}

function block(overrides: Partial<DirectorBlock> = {}): DirectorBlock {
  return {
    key: 'finance.runway_alert',
    doc05_id: '5.4',
    name: 'Cash position and runway',
    shows: 'Balance, burn, runway',
    block: 'metric',
    state: 'planned',
    unlock: 'Needs your accounting system.',
    needs: ['accounting'],
    ...overrides,
  }
}

describe('BlockCard, across every state', () => {
  it('renders every state under its own label', () => {
    // Asserted against `STATE_LABEL` rather than by finding "a chip": the map
    // is the contract the API and this component share, and a test that hunts
    // for an element by shape passes for the wrong reason the moment the markup
    // changes.
    expect(Object.keys(STATE_LABEL).sort()).toEqual([...ALL_STATES].sort())

    const labels = new Set(Object.values(STATE_LABEL))
    expect(labels.size).toBe(ALL_STATES.length)

    for (const state of ALL_STATES) {
      const { unmount } = render(<BlockCard block={block({ state })} />)
      expect(screen.getByText(STATE_LABEL[state])).toBeTruthy()
      unmount()
    }
  })

  it('never renders a zero on a tile with no figure', () => {
    // I10, and **this assertion was narrowed rather than deleted.** It used to
    // cover every state unconditionally, which was right while no tile carried
    // a number. It is now scoped to tiles with no figure, because the rule was
    // never "the character 0 must not appear" — it is that **a zero must not
    // stand in for an absence.** `0 / 65` is a measurement of a page that
    // failed every check, and `0 internal links` is a true observation; a
    // *missing* crawl renders `locked`, which is what says we have not looked.
    //
    // The two cases the old form was really protecting are asserted below and
    // in the test that follows, so the coverage went up, not down.
    for (const state of ALL_STATES) {
      const { container, unmount } = render(<BlockCard block={block({ state })} />)
      expect(container.textContent).not.toMatch(/(^|\s)0(\s|$)/)
      unmount()
    }
  })

  it('renders no number at all where there is no figure', () => {
    // The half of the old zero rule that mattered: not "no 0" but "no digits
    // pretending to be a measurement".
    for (const state of ALL_STATES) {
      const { container, unmount } = render(<BlockCard block={block({ state })} />)
      expect(container.textContent).not.toMatch(/\d+\s*\/\s*\d+/)
      unmount()
    }
  })

  it('renders a locked audit as its unlock, never as a zero score', () => {
    // The case I10 exists for. A workspace whose site could not be read has no
    // signals, so the API sends `locked` and no figure — it must not arrive as
    // 0 out of 65, which would tell a founder their website failed everything.
    const { container } = render(
      <BlockCard
        block={block({ state: 'locked', unlock: 'Needs a read of your website.', figure: null })}
      />,
    )

    expect(screen.getByText('Needs a read of your website.')).toBeTruthy()
    expect(container.textContent).not.toMatch(/0\s*\/\s*65/)
  })

  it('states its unlock when locked, and offers none when planned', () => {
    const { unmount } = render(<BlockCard block={block({ state: 'locked' })} />)
    expect(screen.getByText('Needs your accounting system.')).toBeTruthy()
    unmount()

    // An unbuilt widget cannot be unlocked by connecting anything, and saying
    // otherwise is a promise the product then breaks. The unlock is present in
    // the data and must not be shown.
    render(<BlockCard block={block({ state: 'planned' })} />)
    expect(screen.queryByText('Needs your accounting system.')).toBeNull()
  })

  it('never tells a warming tile to connect anything', () => {
    // The distinction `warming` exists for. `partial` means connect another
    // source; `warming` means wait. Telling somebody to connect what they have
    // already connected is how a product loses trust in its own instructions.
    render(<BlockCard block={block({ state: 'warming' })} />)

    expect(screen.queryByText('Needs your accounting system.')).toBeNull()
    expect(screen.getByText(/nothing to do but wait/i)).toBeTruthy()
  })

  it('says a stale figure is real and out of date, rather than hiding it', () => {
    // Not `live` with a quiet timestamp, and not `unavailable`: the number is
    // real and still worth seeing, with its age attached.
    render(<BlockCard block={block({ state: 'stale' })} />)

    expect(screen.getByText(/real and out of date/i)).toBeTruthy()
  })

  it('labels a self-reported figure as an answer rather than a measurement', () => {
    // Doc 05 §0: a number they typed and a number we measured must never look
    // identical, because the second can contradict them and the first cannot.
    render(<BlockCard block={block({ state: 'self_reported' })} />)

    expect(screen.getByText(/your own answer, not a measurement/i)).toBeTruthy()
  })

  it('offers the working drawer only where there is a figure to explain', () => {
    // The drawer opens onto the checks that produced the number, so offering it
    // on a tile with no number would open onto nothing.
    for (const state of ['live', 'partial', 'stale'] as WidgetState[]) {
      const { unmount } = render(<BlockCard block={block({ state, figure: figure() })} />)
      expect(screen.getByRole('button', { name: /why this number/i })).toBeTruthy()
      unmount()
    }

    for (const state of ['locked', 'warming', 'planned', 'unavailable'] as WidgetState[]) {
      const { unmount } = render(<BlockCard block={block({ state, figure: figure() })} />)
      expect(screen.queryByRole('button', { name: /why this number/i })).toBeNull()
      unmount()
    }
  })

  it('offers no drawer for a figure state that arrived without a figure', () => {
    // **A serving bug, and it must not render as an empty drawer.** The state
    // machine reaches `live` and `partial` by the *absence* of contradicting
    // evidence rather than the presence of a number, so a capability wired
    // reachable with no calculator behind it produces exactly this. The tile
    // falls back to saying what it will draw, which is what every other
    // unbuilt tile says.
    for (const state of ['live', 'partial', 'stale'] as WidgetState[]) {
      const { unmount } = render(<BlockCard block={block({ state, figure: null })} />)
      expect(screen.queryByRole('button', { name: /why this number/i })).toBeNull()
      unmount()
    }
  })
})

describe('BlockCard, with a computed figure', () => {
  it('shows the figure with its denominator, never the bare number', () => {
    // `ShellOut`'s rule for `ShellOut`'s reason: a score on its own is a claim
    // the reader cannot check, and 45 out of 65 lets them count.
    render(<BlockCard block={block({ state: 'partial', figure: figure() })} />)

    expect(screen.getByText('45')).toBeTruthy()
    expect(screen.getByText(/\/ 65/)).toBeTruthy()
  })

  it('does not lead with the percentage', () => {
    // "69%" reads as "69% of your SEO is fine", which is a much stronger claim
    // than "you passed 45 of 65 weighted points". The percentage is served and
    // deliberately not the headline.
    const { container } = render(
      <BlockCard block={block({ state: 'partial', figure: figure() })} />,
    )

    expect(container.textContent).not.toMatch(/69\s*%/)
  })

  it('names what the figure measures, not just what the capability shows', () => {
    // **The guard against the one dishonest thing this slice could ship.**
    // `marketing.brand_intelligence` is presented as "Brand Intelligence" and
    // promises voice consistency; `score_brand` measures whether a first-time
    // visitor can tell what the company does. A correct number under that
    // headline, with no sentence narrowing it, is a lie the reader cannot
    // detect.
    render(
      <BlockCard
        block={block({
          name: 'Brand Intelligence',
          shows: 'Voice consistency, positioning, messaging gaps',
          state: 'partial',
          figure: figure({
            label: 'Site legibility',
            measures:
              'Nine checks on whether a first-time visitor can tell what you do. '
              + 'Not voice consistency, positioning or messaging gaps.',
          }),
        })}
      />,
    )

    expect(screen.getByText(/Not voice consistency/i)).toBeTruthy()
    expect(screen.getByText(/Site legibility/)).toBeTruthy()
  })

  it('renders the date the page was fetched beside the figure', () => {
    // The only thing standing in for the `stale` state the route deliberately
    // does not reach: nothing re-crawls on a schedule, so deriving staleness
    // would mark every audit out of date a week after signup.
    render(<BlockCard block={block({ state: 'partial', figure: figure() })} />)

    expect(screen.getByText(/Measured 2026-09-09/)).toBeTruthy()
  })

  it('links the page the score was measured from', () => {
    // A score whose page cannot be opened is a number nobody can check.
    render(<BlockCard block={block({ state: 'partial', figure: figure() })} />)

    const link = screen.getByRole('link', { name: 'https://muscat-marine.om/' })
    expect(link.getAttribute('href')).toBe('https://muscat-marine.om/')
  })

  it('keeps the unlock alongside the figure rather than instead of it', () => {
    // `partial` means both things are true: there is a real number, and
    // something is still missing. Showing only one of the two is what the
    // deleted `marketing_state` got wrong in each direction.
    render(
      <BlockCard
        block={block({ state: 'partial', unlock: 'Needs keyword data.', figure: figure() })}
      />,
    )

    expect(screen.getByText('45')).toBeTruthy()
    expect(screen.getByText('Needs keyword data.')).toBeTruthy()
  })

  it('opens the working drawer onto the checks that produced the number', () => {
    // `figure.checks` *is* the calculator's working, so the drawer needs no
    // endpoint and no `generation` row. Closed by default: nine rows unfurled
    // on every tile would bury the number they explain.
    render(<BlockCard block={block({ state: 'partial', figure: figure() })} />)

    expect(screen.queryByText('Served over HTTPS')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /why this number/i }))

    expect(screen.getByText('Served over HTTPS')).toBeTruthy()
    expect(screen.getByText('0 internal links')).toBeTruthy()
    expect(screen.getByText('calculators.audit.score_technical_seo')).toBeTruthy()
  })

  it('shows a failed check as an observation, not as an error', () => {
    // A page without structured data has not done anything wrong. Nine rows
    // styled red would turn the calculator's observations into a reprimand.
    render(<BlockCard block={block({ state: 'partial', figure: figure() })} />)
    fireEvent.click(screen.getByRole('button', { name: /why this number/i }))

    // The evidence is carried through in the calculator's words, unrestated
    // into advice — "0 internal links", never "add internal links".
    expect(screen.getByText('0 internal links')).toBeTruthy()
    expect(screen.queryByText(/^add /i)).toBeNull()
  })
})

describe('BlockCard, across every kind', () => {
  it('says what each of the nine will draw, and says something different for each', () => {
    // A kind with no promise of its own is a kind nobody has thought about —
    // the same failure as an unreachable state. Nine distinct sentences is the
    // assertion that the vocabulary is doing work.
    const promises = new Set<string>()

    for (const kind of ALL_KINDS) {
      const { container, unmount } = render(
        <BlockCard block={block({ block: kind, state: 'planned' })} />,
      )
      const text = container.textContent ?? ''
      expect(text).toContain(kind)
      promises.add(text)
      unmount()
    }

    expect(promises.size).toBe(ALL_KINDS.length)
  })

  it('carries the canonical id, and the doc 05 number only when there is one', () => {
    const { unmount } = render(<BlockCard block={block()} />)
    expect(screen.getByText('finance.runway_alert')).toBeTruthy()
    expect(screen.getByText('5.4')).toBeTruthy()
    unmount()

    // The thirteen capabilities doc 08 specified and doc 05 never did. An empty
    // reference rendered as a chip would be a label pointing at no paragraph.
    render(<BlockCard block={block({ key: 'finance.approvals_queue', doc05_id: '' })} />)
    expect(screen.getByText('finance.approvals_queue')).toBeTruthy()
    expect(screen.queryByText('5.4')).toBeNull()
  })
})
