import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DepartmentsCard } from '@/components/settings/DepartmentsCard'

/**
 * Panel 7. The screen has to say what a change costs *before* it happens.
 *
 * The failure it guards against is a checkbox that quietly takes a director off
 * somebody's nav. So the assertions are about the two consequence lines and
 * about the floor of one — finding F1, where a stored selection of none reads as
 * "nothing ruled out" and hands back all seven directors.
 */

const PAYLOAD = {
  may_administer: true,
  departments: [
    { value: 'finance', label: 'Finance', running: true, capabilities: 11, answered: 4, unanswered: 0 },
    { value: 'marketing', label: 'Marketing', running: false, capabilities: 12, answered: 0, unanswered: 5 },
  ],
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => json(PAYLOAD)))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DepartmentsCard', () => {
  it('says what each department brings before it is ticked', async () => {
    render(<DepartmentsCard />)

    await waitFor(() => expect(screen.getByText('Marketing')).toBeTruthy())
    // Derived by the API from the registry — a count this component made up
    // would be the one number on the screen nobody could check.
    expect(screen.getByText(/12 capabilities · 5 questions unanswered/)).toBeTruthy()
  })

  it('warns what removing one costs, while the checkbox is still untickable', async () => {
    render(<DepartmentsCard />)

    await waitFor(() => expect(screen.getByText('Finance')).toBeTruthy())
    fireEvent.click(screen.getByRole('checkbox', { name: /Finance/ }))

    expect(screen.getByText(/takes its director off the nav/)).toBeTruthy()
    // Q32. Deleting the answers would lose the evidence a later disagreement
    // needs, so the screen promises they stay.
    expect(screen.getByText(/answers stay/i)).toBeTruthy()
  })

  it('says what adding one brings, including the questions', async () => {
    render(<DepartmentsCard />)

    await waitFor(() => expect(screen.getByText('Marketing')).toBeTruthy())
    fireEvent.click(screen.getByRole('checkbox', { name: /Marketing/ }))

    expect(screen.getByText(/creates its director and its question block/)).toBeTruthy()
  })

  it('refuses to save an empty selection, and says why', async () => {
    render(<DepartmentsCard />)

    await waitFor(() => expect(screen.getByText('Finance')).toBeTruthy())
    fireEvent.click(screen.getByRole('checkbox', { name: /Finance/ }))

    // Finding F1: with none chosen there is nothing for the Chief of Staff to
    // read, and the stored state would be indistinguishable from "not chosen
    // yet" — which hands back all seven.
    expect(screen.getByText(/Keep at least one/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Save departments/ })).toHaveProperty(
      'disabled',
      true,
    )
  })

  it('shows a reader the departments without offering to change them', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({ ...PAYLOAD, may_administer: false })),
    )
    render(<DepartmentsCard />)

    await waitFor(() => expect(screen.getByText(/Set by an owner or an executive/)).toBeTruthy())
    expect(screen.queryByRole('button', { name: /Save departments/ })).toBeNull()
    expect(screen.getByRole('checkbox', { name: /Finance/ })).toHaveProperty('disabled', true)
  })
})
