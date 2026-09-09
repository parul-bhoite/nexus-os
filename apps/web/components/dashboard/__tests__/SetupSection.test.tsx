import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NotAskedPanel, SetupSection } from '@/components/dashboard/SetupSection'

/**
 * The day-one tabs. `doc/13` §4 and §9.
 *
 * The rule that matters most here is `doc/05` §0: **a number they typed and a
 * number we measured must never look identical**, because the second can
 * contradict them and the first cannot. So the assertions are about treatment —
 * an answer is quoted and attributed, never set as a figure.
 */

const SETUP = {
  department: 'finance',
  facts: [
    {
      key: 'runway_alert_months',
      question: 'How many months of runway would worry you?',
      answer: 'under 6',
      answered_at: '2026-09-01T10:00:00+00:00',
      reads_it: 'finance.runway_alert',
    },
  ],
  watch: [] as never[],
}

const WATCH = {
  department: 'operations',
  facts: [] as never[],
  watch: [
    {
      key: 'supplier_concentration',
      label: 'Supplier concentration',
      stated: 'One valve supplier, roughly a third of purchases',
      answered_at: '2026-09-01T10:00:00+00:00',
      measured_by: 'What share of purchases actually goes to that supplier.',
      needs: 'purchase history in the operations layer',
    },
  ],
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      new Response(JSON.stringify(url.includes('operations') ? WATCH : SETUP), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SetupSection', () => {
  it('quotes the answer and attributes it, rather than presenting a figure', async () => {
    render(<SetupSection department="finance" tab="setup" notAsked={[]} />)

    // The quotation marks are the treatment. Without them "under 6" beside a
    // question reads as something the product worked out.
    await waitFor(() => expect(screen.getByText(/“under 6”/)).toBeTruthy())
    expect(screen.getByText(/^You,/)).toBeTruthy()
  })

  it('names what reads each answer', async () => {
    // Q33 turned outward: the founder can see what their answer is *for*.
    render(<SetupSection department="finance" tab="setup" notAsked={[]} />)

    await waitFor(() =>
      expect(screen.getByText(/reads it: finance\.runway_alert/)).toBeTruthy(),
    )
  })

  it('carries the date the answer was given', async () => {
    // An answer from four months ago and one from yesterday warrant different
    // confidence, and nothing else on the page can tell a reader which is which.
    render(<SetupSection department="finance" tab="setup" notAsked={[]} />)

    await waitFor(() => expect(screen.getByText(/You, \d/)).toBeTruthy())
  })

  it('pairs a watch item with what will test it and what that needs', async () => {
    render(<SetupSection department="operations" tab="watchlist" notAsked={[]} />)

    await waitFor(() => expect(screen.getByText('Supplier concentration')).toBeTruthy())
    expect(screen.getByText(/What share of purchases/)).toBeTruthy()
    expect(screen.getByText(/Needs purchase history/)).toBeTruthy()
  })

  it('says nothing is being watched rather than inventing a risk', async () => {
    render(<SetupSection department="finance" tab="watchlist" notAsked={[]} />)

    await waitFor(() =>
      expect(screen.getByText(/nothing being watched rather than nothing to watch/i)).toBeTruthy(),
    )
  })

  it('explains an empty Setup as unanswered questions, not as missing access', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ department: 'sales', facts: [], watch: [] }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
      ),
    )
    render(<SetupSection department="sales" tab="setup" notAsked={[]} />)

    await waitFor(() =>
      expect(screen.getByText(/Nobody has answered this department/i)).toBeTruthy(),
    )
  })
})

describe('NotAskedPanel', () => {
  it('names each figure and the source it is read from', () => {
    // Doc 08 §11's second addition: showing the customer what NEXUS refuses to
    // ask them is a product surface, not just an internal rule.
    render(
      <NotAskedPanel
        entries={[{ what: 'Bank balances, invoices and ledger detail', source: 'your accounting system' }]}
      />,
    )

    expect(screen.getByText(/Bank balances/)).toBeTruthy()
    expect(screen.getByText(/read from your accounting system/)).toBeTruthy()
  })

  it('renders nothing when there is nothing to disclose', () => {
    const { container } = render(<NotAskedPanel entries={[]} />)

    expect(container.firstChild).toBeNull()
  })
})
