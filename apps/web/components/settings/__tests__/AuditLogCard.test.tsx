import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuditLogCard } from '@/components/settings/AuditLogCard'

/**
 * Panel 12. The log's value is that it records refusals, and the panel says so.
 */

const ENTRIES = {
  entries: [
    {
      action: 'departments_changed',
      actor_user_id: '11111111-1111-1111-1111-111111111111',
      target_type: 'workspace',
      target_id: '22222222-2222-2222-2222-222222222222',
      reason: 'added marketing; removed none',
      at: '2026-09-09T10:00:00+00:00',
    },
    {
      action: 'answer_written',
      actor_user_id: null,
      target_type: null,
      target_id: null,
      reason: null,
      at: '2026-09-09T09:00:00+00:00',
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
  vi.stubGlobal('fetch', vi.fn(async () => respond(ENTRIES)))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AuditLogCard', () => {
  it('says refusals are recorded, not only successes', async () => {
    // The reason to show the log at all. A log that records only what worked
    // cannot tell you that somebody probed.
    render(<AuditLogCard />)

    await waitFor(() => expect(screen.getByText(/Refusals are recorded/)).toBeTruthy())
  })

  it('renders an action in words rather than as a key', async () => {
    render(<AuditLogCard />)

    await waitFor(() => expect(screen.getByText('departments changed')).toBeTruthy())
    expect(screen.getByText(/added marketing/)).toBeTruthy()
  })

  it('renders a dash where a row has no object, never a blank cell', async () => {
    // An empty cell reads as data we lost rather than as an action with no
    // object.
    render(<AuditLogCard />)

    await waitFor(() => expect(screen.getByText('answer written')).toBeTruthy())
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('names the gap rather than inventing an actor', async () => {
    // The API returns a user id. A UUID is useless to a human and "a user" is a
    // fiction, so the panel says what it does not have.
    render(<AuditLogCard />)

    await waitFor(() => expect(screen.getByText(/Who did each one is stored/)).toBeTruthy())
  })

  it('renders nothing at all for a caller the API refuses', async () => {
    // 403 is the ordinary answer for most people. A red box telling somebody
    // they may not read something they never asked for is worse than absence.
    vi.stubGlobal('fetch', vi.fn(async () => respond({ detail: 'Forbidden' }, 403)))
    const { container } = render(<AuditLogCard />)

    await waitFor(() => expect(container.firstChild).toBeNull())
  })

  it('says nothing has happened yet rather than showing an empty table', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond({ entries: [] })))
    render(<AuditLogCard />)

    await waitFor(() => expect(screen.getByText(/Nothing recorded yet/)).toBeTruthy())
    expect(screen.queryByRole('table')).toBeNull()
  })
})
