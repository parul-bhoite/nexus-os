import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DocumentLibrary } from '@/components/documents/DocumentLibrary'
import {
  type StoredDocument,
  type UploadStage,
  listDocuments,
  readAsks,
  requestDownload,
  uploadDocument,
} from '@/lib/documents-client'

/**
 * H4's upload half.
 *
 * The cases worth testing are the two that *look* like success: a file the
 * browser refused before sending, and a file the server stored and could not
 * read. Both leave a person believing NEXUS has something it does not, which is
 * the failure this product can least afford.
 */

vi.mock('@/lib/documents-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/documents-client')>()
  return {
    ...actual,
    readAsks: vi.fn(),
    listDocuments: vi.fn(),
    uploadDocument: vi.fn(),
    requestDownload: vi.fn(),
  }
})

const STAGE: UploadStage = {
  consent: { text: 'you are entitled to share it.', version: 'v1' },
  departments: [],
  max_file_bytes: 25 * 1024 * 1024,
  max_files_at_onboarding: 10,
  workspace_quota_bytes: 100 * 1024 * 1024,
  bytes_used: 10 * 1024 * 1024,
  files_uploaded: 1,
}

const INDEXED: StoredDocument = {
  document_id: 'dddddddd-0000-0000-0000-000000000001',
  filename: 'price-list.pdf',
  status: 'indexed',
  page_count: 4,
  failure_reason: null,
  created_at: '2026-09-19T00:00:00Z',
  chunks_held_for_review: 0,
}

function withDocuments(...documents: StoredDocument[]) {
  vi.mocked(readAsks).mockResolvedValue(STAGE)
  vi.mocked(listDocuments).mockResolvedValue(documents)
}

function choose(file: File) {
  const input = screen.getByLabelText(/add a document/i)
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  fireEvent.change(input)
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('DocumentLibrary', () => {
  it('states the limit from the server rather than a number of its own', async () => {
    withDocuments()
    render(<DocumentLibrary />)

    await waitFor(() => expect(screen.getByText(/Up to 25 MB each/)).toBeTruthy())
  })

  it('lists what was already sent, with its page count', async () => {
    withDocuments(INDEXED)
    render(<DocumentLibrary />)

    await waitFor(() => expect(screen.getByText('price-list.pdf')).toBeTruthy())
    expect(screen.getByText('4 pages')).toBeTruthy()
  })

  it('says a stored-but-unreadable file is unreadable, and why', async () => {
    // The 422 case. The row exists, so "upload failed" would be a lie; the
    // parser's reason is the only part anybody can act on.
    withDocuments({
      ...INDEXED,
      filename: 'scan.pdf',
      status: 'failed',
      page_count: null,
      failure_reason: 'No text layer — this looks like a scan.',
    })
    render(<DocumentLibrary />)

    await waitFor(() => expect(screen.getByText('unreadable')).toBeTruthy())
    expect(screen.getByText(/No text layer/)).toBeTruthy()
  })

  it('refuses an oversized file without sending it, and says so', async () => {
    withDocuments()
    render(<DocumentLibrary />)
    await waitFor(() => expect(screen.getByLabelText(/add a document/i)).toBeTruthy())

    const huge = new File(['x'], 'huge.pdf', { type: 'application/pdf' })
    Object.defineProperty(huge, 'size', { value: STAGE.max_file_bytes + 1 })
    choose(huge)

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/huge\.pdf/))
    expect(uploadDocument, 'an over-limit file must not reach the wire').not.toHaveBeenCalled()
  })

  it('points at the review queue when something is withheld', async () => {
    // Withheld is not rejected, and a screen that showed the upload as done
    // without saying anything is waiting would be the whole gap ADR 0051 left.
    withDocuments({ ...INDEXED, chunks_held_for_review: 3 })
    render(<DocumentLibrary />)

    await waitFor(() => expect(screen.getByText(/3 passages are withheld/)).toBeTruthy())
    expect(screen.getByRole('link', { name: /review them/i }).getAttribute('href')).toBe(
      '/review-queue',
    )
  })

  it('re-reads the list after an upload instead of trusting the response', async () => {
    withDocuments()
    vi.mocked(uploadDocument).mockResolvedValue({
      document_id: INDEXED.document_id,
      filename: 'price-list.pdf',
      status: 'indexed',
      chunks_indexed: 9,
      chunks_held_for_review: 0,
      page_count: 4,
      message: '',
    })
    render(<DocumentLibrary />)
    await waitFor(() => expect(screen.getByLabelText(/add a document/i)).toBeTruthy())

    vi.mocked(listDocuments).mockResolvedValue([INDEXED])
    choose(new File(['x'], 'price-list.pdf', { type: 'application/pdf' }))

    // Twice: once on mount, once after the upload. The row carries what the
    // classifier decided, which the upload response does not.
    await waitFor(() => expect(vi.mocked(listDocuments).mock.calls.length).toBe(2))
    expect(screen.getByText('price-list.pdf')).toBeTruthy()
  })

  it('mints a signed link on demand and sends the browser to it', async () => {
    // Two steps, not one. The link is authorised here, against the uploader,
    // and fetched afterwards with no session — so the component must ask for
    // one per click rather than holding a URL that outlives its own expiry.
    withDocuments(INDEXED)
    vi.mocked(requestDownload).mockResolvedValue({
      url: '/files/ws/doc?expires=1&sig=abc',
      expires_in_seconds: 300,
    })
    const assign = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { assign },
      writable: true,
    })
    render(<DocumentLibrary />)
    await waitFor(() => expect(screen.getByText('price-list.pdf')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Download' }))

    await waitFor(() => expect(assign).toHaveBeenCalledWith('/files/ws/doc?expires=1&sig=abc'))
    expect(requestDownload).toHaveBeenCalledWith(INDEXED.document_id)
  })

  it('offers a download for a file that could not be read', async () => {
    // The case where it matters most: somebody needs the scan back to see
    // what they actually sent.
    withDocuments({
      ...INDEXED,
      filename: 'scan.pdf',
      status: 'failed',
      page_count: null,
      failure_reason: 'No text layer — this looks like a scan.',
    })
    render(<DocumentLibrary />)

    await waitFor(() => expect(screen.getByText('scan.pdf')).toBeTruthy())
    expect(screen.getByRole('button', { name: 'Download' })).toBeTruthy()
  })

  it('says so against the row when a link cannot be minted', async () => {
    withDocuments(INDEXED)
    vi.mocked(requestDownload).mockRejectedValue(new Error('No such document.'))
    render(<DocumentLibrary />)
    await waitFor(() => expect(screen.getByText('price-list.pdf')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Download' }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('No such document.'))
  })
})
