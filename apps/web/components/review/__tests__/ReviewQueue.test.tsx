import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewQueue } from '@/components/review/ReviewQueue'
import { AuthError } from '@/lib/auth-client'
import { decideChunk, readReviewQueue } from '@/lib/review-queue-client'

/**
 * H4's screen, and the properties that make it a control rather than a list.
 *
 * The queue holds content withheld from everyone but its uploader, so the
 * failure that matters here is not a broken render — it is a decision the
 * reviewer believes they made. A refused approval that disappears from the
 * screen reads exactly like a successful one.
 */

vi.mock('@/lib/review-queue-client', () => ({
  readReviewQueue: vi.fn(),
  decideChunk: vi.fn(),
}))

const ITEM = {
  chunk_id: 'aaaaaaaa-0000-0000-0000-000000000001',
  document_id: 'bbbbbbbb-0000-0000-0000-000000000001',
  filename: 'payroll.xlsx',
  source_page: 3,
  source_label: null,
  excerpt: 'Basic pay and allowances by employee for the quarter.',
  scope: 'l5',
  sensitivity: 'personal',
  confidence: 1,
  classified_by: 'rules-v1',
}

function queued(...items: (typeof ITEM)[]) {
  vi.mocked(readReviewQueue).mockResolvedValue({ items, total: items.length })
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('ReviewQueue', () => {
  it('shows the excerpt with the decision that withheld it', async () => {
    queued(ITEM)
    render(<ReviewQueue />)

    await waitFor(() => expect(screen.getByText(/Basic pay and allowances/)).toBeTruthy())
    // Which classifier, and how sure — a reviewer checking a confident
    // pattern match is doing different work from one checking a shrug.
    expect(screen.getByText(/rules-v1 · 1\.00/)).toBeTruthy()
    expect(screen.getByText('personal')).toBeTruthy()
  })

  it('says nothing is waiting rather than rendering an empty list', async () => {
    queued()
    render(<ReviewQueue />)

    await waitFor(() =>
      expect(screen.getByText(/Nothing is waiting for a decision/)).toBeTruthy(),
    )
  })

  it('sends the chosen scope and takes the item off the queue', async () => {
    queued(ITEM)
    vi.mocked(decideChunk).mockResolvedValue(undefined)
    render(<ReviewQueue />)
    await waitFor(() => expect(screen.getByText(/Basic pay/)).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Its department' }))

    await waitFor(() => expect(screen.queryByText(/Basic pay/)).toBeNull())
    expect(decideChunk).toHaveBeenCalledWith(ITEM.chunk_id, { approve: true, scope: 'l3' })
  })

  it('sends a rejection as a rejection, not an approval with no scope', async () => {
    // F-05: "Reject" now confirms before it fires — a one-click rejection
    // used to discard knowledge with the consequence stated only in a
    // `title` tooltip. The row's button opens the dialog; the dialog's own
    // "Reject" is what actually decides.
    queued(ITEM)
    vi.mocked(decideChunk).mockResolvedValue(undefined)
    render(<ReviewQueue />)
    await waitFor(() => expect(screen.getByText(/Basic pay/)).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Reject' }))
    expect(decideChunk).not.toHaveBeenCalled()

    const dialog = await screen.findByRole('dialog', { name: /reject this passage/i })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reject' }))

    await waitFor(() => expect(decideChunk).toHaveBeenCalledWith(ITEM.chunk_id, { approve: false }))
  })

  it('keeps a refused item on screen and shows why', async () => {
    // The case this screen exists to get right. `may_reach_scope` refuses an
    // approval into a scope the reviewer does not hold; if the row vanished,
    // they would believe the chunk is now company-visible when it is not.
    queued(ITEM)
    vi.mocked(decideChunk).mockRejectedValue(
      new AuthError('You cannot approve a chunk into a scope you do not have access to.', 403),
    )
    render(<ReviewQueue />)
    await waitFor(() => expect(screen.getByText(/Basic pay/)).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Whole company' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        /cannot approve a chunk into a scope you do not have access to/,
      ),
    )
    expect(screen.getByText(/Basic pay/), 'a refused chunk must not look decided').toBeTruthy()
  })

  it('offers no way to place a chunk at L4', async () => {
    // L4 is reachable only by being named on the item, so an L4 button would
    // be a UI convention standing in for a boundary — `may_reach_scope`
    // refuses it outright.
    queued(ITEM)
    render(<ReviewQueue />)
    await waitFor(() => expect(screen.getByText(/Basic pay/)).toBeTruthy())

    const labels = screen.getAllByRole('button').map((b) => b.textContent ?? '')
    expect(labels.join(' ')).not.toMatch(/l4|restricted/i)
  })
})
