import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AssistantPanel } from '@/components/dashboard/AssistantPanel'

/**
 * Reserved, and honest about it. **Q67**, and `doc/20` A0's **pin**.
 *
 * The panel's own docstring is the specification: *"an input that accepts a
 * question and cannot answer it is worse than none: somebody types the thing
 * they most want to know and gets silence, and the next thing they conclude is
 * that the product does not work."*
 *
 * That holds until the assistant can answer, and "can answer" has a gate:
 * injection evals that could actually fail. The current ten are assertions over
 * a dataclass — no model, no prompt, no retrieval — so they establish that the
 * taint model is specified, not that an assistant resists injection. The gate is
 * shut.
 *
 * **This test is green today and must stay green through every step of `doc/20`
 * except the last.** It is the thing that makes "not yet" enforceable rather
 * than remembered, on a build that will get steadily closer to having something
 * to put in a box.
 */

const RESERVED = {
  director: 'AI Finance Advisor',
  questions: ['What are our payment terms?', 'What does the contract say about late payment?'],
  available: false,
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

  it('renders nothing at all once available, rather than a half-built chat', () => {
    // P20 replaces this panel. Rendering both would show a founder two
    // assistants, and a placeholder chat here would be the shortcut the
    // component's own docstring refuses.
    const { container } = render(<AssistantPanel assistant={{ ...RESERVED, available: true }} />)

    expect(container.firstChild).toBeNull()
  })
})
