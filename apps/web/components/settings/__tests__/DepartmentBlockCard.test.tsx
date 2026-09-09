import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DepartmentBlockCard } from '@/components/settings/DepartmentBlockCard'

/**
 * Panel 3, and the two authority rules it must not guess.
 *
 * `may_answer` and `binds` are served. A Contributor shown a form that binds,
 * or a Manager shown a read-only block for their own department, are the two
 * wrong guesses — so both are asserted from the payload rather than from a role
 * string.
 */

const BLOCK = {
  department: 'finance',
  may_answer: true,
  binds: true,
  questions: [
    {
      key: 'payment_terms',
      prompt: 'Standard payment terms you offer?',
      why: 'The ageing buckets, and what counts as overdue.',
      answer_type: 'single_choice',
      consumed_by: 'finance.receivables_ageing',
      answered: true,
      proposed: false,
      answer: '30 days',
    },
  ],
}

function respond(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => respond(BLOCK)))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DepartmentBlockCard', () => {
  it('shows each question with why it is asked and what reads the answer', async () => {
    render(<DepartmentBlockCard department="finance" label="Finance" />)

    await waitFor(() => expect(screen.getByText(/ageing buckets/)).toBeTruthy())
    // Q33 made visible to the person answering.
    expect(screen.getByText(/reads it: finance\.receivables_ageing/)).toBeTruthy()
  })

  it('offers no save to a caller who may not answer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond({ ...BLOCK, may_answer: false })))
    render(<DepartmentBlockCard department="finance" label="Finance" />)

    await waitFor(() => expect(screen.getByText(/Read-only for you/)).toBeTruthy())
    expect(screen.queryByRole('button', { name: /Save answers/ })).toBeNull()
    // Still shown: somebody is entitled to see what their own figures are
    // measured against.
    expect(screen.getByText(/Standard payment terms/)).toBeTruthy()
  })

  it('tells a Contributor their answer is a proposal, and says so on the button', async () => {
    // Q31/D22. Somebody who thinks they have set a threshold and has not would
    // find out from a figure that did not move.
    vi.stubGlobal('fetch', vi.fn(async () => respond({ ...BLOCK, binds: false })))
    render(<DepartmentBlockCard department="finance" label="Finance" />)

    // Matched on a phrase inside one text node: the sentence is split by a
    // <strong>, and a regex across the whole paragraph fails for a reason that
    // has nothing to do with the behaviour.
    await waitFor(() =>
      expect(screen.getByText(/manager confirms them at the review gate/)).toBeTruthy(),
    )
    expect(screen.getByRole('button', { name: /Propose answers/ })).toBeTruthy()
  })

  it('renders nothing for a department this caller cannot reach', async () => {
    // The dashboard's rule: how a company is organised is itself a fact about
    // it, so absence rather than an explanation.
    vi.stubGlobal('fetch', vi.fn(async () => respond({ detail: 'Not found' }, 404)))
    const { container } = render(<DepartmentBlockCard department="finance" label="Finance" />)

    await waitFor(() => expect(container.firstChild).toBeNull())
  })
})
