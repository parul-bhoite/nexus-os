import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { EntitiesCard } from '@/components/settings/EntitiesCard'

/**
 * Panel 4b. It answers *"which company are these settings about?"* — a question
 * that has an answer whether or not there is a second one.
 */

const TWO = {
  workspaces: [
    { workspace_id: 'ws-1', name: 'Entity One', role: 'owner', active: true },
    { workspace_id: 'ws-2', name: 'Entity Two', role: 'department_manager', active: false },
  ],
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

let assigned: string[] = []

beforeEach(() => {
  assigned = []
  vi.stubGlobal('fetch', vi.fn(async () => json(TWO)))
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, assign: (url: string) => assigned.push(url) },
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('EntitiesCard', () => {
  it('names which entity every other panel belongs to', async () => {
    render(<EntitiesCard />)

    await waitFor(() => expect(screen.getByText(/Everything else on this screen/)).toBeTruthy())
    // Twice on purpose: named in the sentence that says what the other panels
    // are about, and again in the list as the active row.
    expect(screen.getAllByText('Entity One')).toHaveLength(2)
  })

  it('shows the role held at each entity, because it differs', async () => {
    // An Owner at one company and a Sales manager at another is the ordinary
    // case for a group finance director — and being an Owner of one grants
    // nothing at the next.
    render(<EntitiesCard />)

    await waitFor(() => expect(screen.getByText(/You are owner here · active/)).toBeTruthy())
    expect(screen.getByText(/You are department manager here/)).toBeTruthy()
  })

  it('renders for a single-entity account, unlike the shell switcher', async () => {
    // Here the panel answers "which company are these settings about?", which
    // has an answer regardless.
    vi.stubGlobal('fetch', vi.fn(async () => json({ workspaces: [TWO.workspaces[0]] })))
    render(<EntitiesCard />)

    await waitFor(() => expect(screen.getByText('Your company')).toBeTruthy())
    expect(screen.queryByRole('button', { name: /Switch to this/ })).toBeNull()
  })

  it('reloads the settings screen after a switch rather than re-rendering it', async () => {
    // Every panel on this screen was read under the previous entity.
    render(<EntitiesCard />)

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Switch to this/ })).toBeTruthy(),
    )
    fireEvent.click(screen.getByRole('button', { name: /Switch to this/ }))

    await waitFor(() => expect(assigned).toEqual(['/settings?switched=1']))
  })

  it('says the group view is not built rather than linking to nothing', async () => {
    // It needs a per-entity figure to roll up, and none is computable yet.
    render(<EntitiesCard />)

    await waitFor(() => expect(screen.getByText(/group view across all 2 is not built/)).toBeTruthy())
  })
})
