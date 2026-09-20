// `fireEvent`, not `user-event`: the latter is not a dependency here, and this
// repository has no lockfile (finding #16), so every added package is one more
// thing CI resolves differently from every developer. Nothing below needs the
// fidelity user-event buys.
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AssistantPanel } from '@/components/dashboard/AssistantPanel'

/**
 * **Q67, and `doc/20` A0's pin — which is now half spent, on purpose.**
 *
 * The panel's docstring is still the specification: *"an input that accepts a
 * question and cannot answer it is worse than none: somebody types the thing
 * they most want to know and gets silence, and the next thing they conclude is
 * that the product does not work."*
 *
 * That held until the assistant could answer, and "can answer" had a gate:
 * injection evals that could actually fail. A0 wrote *"this test is green today
 * and must stay green through every step of `doc/20` except the last"*. A2 and
 * A3 built the evals that can fail, A6–A9 built the path and proved the scope
 * boundary, and A11 is that last step — so **the unavailable half stays pinned
 * exactly as it was**, and the available half is new.
 *
 * One test was removed rather than adapted: *"renders nothing at all once
 * available, rather than a half-built chat"*. It asserted this component would
 * be **replaced** by P20. It is not — it is P20 — so the assertion described an
 * implementation route, not a guarantee. Its actual concern, that a founder
 * must never see two assistants, is unchanged and unviolated: there is one
 * panel.
 */

const RESERVED = {
  director: 'AI Finance Advisor',
  questions: ['What are our payment terms?', 'What does the contract say about late payment?'],
  available: false,
}

const AVAILABLE = { ...RESERVED, available: true }

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function answersWith(payload: Record<string, unknown>) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => payload,
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('AssistantPanel while the assistant is unavailable', () => {
  it('offers nothing to type into', () => {
    const { container } = render(<AssistantPanel assistant={RESERVED} />)

    expect(container.querySelector('input')).toBeNull()
    expect(container.querySelector('textarea')).toBeNull()
    expect(container.querySelector('form')).toBeNull()
    expect(container.querySelector('[contenteditable]')).toBeNull()
  })

  it('names the director and lists what it will answer', () => {
    render(<AssistantPanel assistant={RESERVED} />)

    expect(screen.getByText(/Ask the AI Finance Advisor/)).toBeTruthy()
    expect(screen.getByText(/What are our payment terms\?/)).toBeTruthy()
  })

  it('says what it will read, not just that it is coming', () => {
    // ADR 0052. A reserved panel that promises "answers" in the abstract sets
    // the reader up to expect a runway figure; naming documents as the source
    // is what makes the question list above a promise rather than a tease.
    render(<AssistantPanel assistant={RESERVED} />)

    expect(screen.getByText(/documents this workspace has uploaded/)).toBeTruthy()
    expect(screen.getByText(/Not available yet/)).toBeTruthy()
  })
})

describe('AssistantPanel once the assistant is available', () => {
  it('offers exactly one thing to type into', () => {
    const { container } = render(
      <AssistantPanel assistant={AVAILABLE} department="finance" />,
    )

    expect(container.querySelectorAll('textarea')).toHaveLength(1)
    expect(container.querySelector('input')).toBeNull()
    expect(screen.queryByText(/Not available yet/)).toBeNull()
  })

  it('renders an answer with one citation link per cited passage', async () => {
    answersWith({
      answered: true,
      prose: 'Payment is due within 30 days.',
      citations: [
        {
          chunk_id: 'c1',
          document_id: 'd1',
          source_label: 'terms.pdf',
          source_page: 4,
        },
      ],
      reason: null,
      sentence: null,
    })

    render(<AssistantPanel assistant={AVAILABLE} department="finance" />)
    fireEvent.change(screen.getByLabelText(/Ask a question/), { target: { value: 'terms?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() => {
      expect(screen.getByText('Payment is due within 30 days.')).toBeTruthy()
    })
    const links = screen.getAllByTestId('assistant-citation')
    expect(links).toHaveLength(1)
    // Followable, which is the whole reason a citation exists. A link that does
    // not open the passage is decoration, and the numeral rule behind the
    // answer is only meaningful if a reader can check it.
    // `#doc-<id>`, because there is no per-document page. Pinned as the exact
    // string: the first version of this linked to `/documents/d1` and every
    // citation 404ed in the browser while this test stayed green.
    expect(links[0].getAttribute('href')).toBe('/documents#doc-d1')
    expect(links[0].textContent).toContain('terms.pdf')
    expect(links[0].textContent).toContain('page 4')
  })

  it('renders a refusal as its sentence alone, with no citations', async () => {
    // **The sentence is the whole response.** `doc/20` §5 Q6.2 makes it the one
    // string that must not vary with who is asking or what exists, so this
    // component must not decorate it, prefix it, or pair it with a "try
    // rephrasing" of its own invention. A citation beside a refusal would also
    // be a disclosure — it would name a passage the answer did not use.
    answersWith({
      answered: false,
      prose: '',
      citations: [],
      reason: 'no_passage',
      sentence: 'Nothing in the documents this workspace has uploaded covers that.',
    })

    render(<AssistantPanel assistant={AVAILABLE} department="finance" />)
    fireEvent.change(screen.getByLabelText(/Ask a question/), { target: { value: 'runway?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() => {
      expect(screen.getByTestId('assistant-refusal').textContent).toBe(
        'Nothing in the documents this workspace has uploaded covers that.',
      )
    })
    expect(screen.queryAllByTestId('assistant-citation')).toHaveLength(0)
  })

  it('distinguishes a failed exchange from a refusal', async () => {
    // Collapsing the two would teach a founder to distrust every honest
    // refusal: "your documents do not cover that" and "we could not reach the
    // assistant" are different facts about their business.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }))

    render(<AssistantPanel assistant={AVAILABLE} department="finance" />)
    fireEvent.change(screen.getByLabelText(/Ask a question/), { target: { value: 'terms?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() => {
      expect(screen.getByText(/Cannot reach the assistant/)).toBeTruthy()
    })
    expect(screen.queryByTestId('assistant-refusal')).toBeNull()
  })

  it('will not send an empty question', async () => {
    const fetchMock = answersWith({ answered: false, sentence: 'x', citations: [] })

    render(<AssistantPanel assistant={AVAILABLE} department="finance" />)
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

    expect(fetchMock).not.toHaveBeenCalled()
  })
})
