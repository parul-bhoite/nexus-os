import { render, screen } from '@testing-library/react'
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

  it('never renders a zero in any state', () => {
    // I10. A `0` on a tile is a statement about the customer's business, and
    // the states that have no figure must not reach for a placeholder one.
    for (const state of ALL_STATES) {
      const { container, unmount } = render(<BlockCard block={block({ state })} />)
      expect(container.textContent).not.toMatch(/(^|\s)0(\s|$)/)
      unmount()
    }
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
    // The drawer opens onto the `generation` row behind the number. Offering it
    // on a tile with no number would open onto nothing.
    for (const state of ['live', 'partial', 'stale'] as WidgetState[]) {
      const { unmount } = render(<BlockCard block={block({ state })} />)
      expect(screen.getByRole('button', { name: /why this number/i })).toBeTruthy()
      unmount()
    }

    for (const state of ['locked', 'warming', 'planned', 'unavailable'] as WidgetState[]) {
      const { unmount } = render(<BlockCard block={block({ state })} />)
      expect(screen.queryByRole('button', { name: /why this number/i })).toBeNull()
      unmount()
    }
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
