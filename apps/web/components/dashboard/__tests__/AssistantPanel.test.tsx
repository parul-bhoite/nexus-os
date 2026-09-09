import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AssistantPanel } from '@/components/dashboard/AssistantPanel'

/**
 * Reserved, and honest about it. Q67.
 *
 * A blank region where a feature is coming reads as a bug; a fake one reads as
 * a lie. The panel's job before P20 is to name what it will do.
 */

const FINANCE = {
  director: 'AI Finance Advisor',
  questions: ['What is our cash position?', 'Who owes us and how late are they?'],
  available: false,
}

describe('AssistantPanel', () => {
  it('names the director and the questions it will answer', () => {
    render(<AssistantPanel assistant={FINANCE} />)

    expect(screen.getByText(/AI Finance Advisor/)).toBeTruthy()
    expect(screen.getByText(/What is our cash position\?/)).toBeTruthy()
  })

  it('says it is not available rather than implying it is', () => {
    render(<AssistantPanel assistant={FINANCE} />)

    expect(screen.getByText(/not available yet/i)).toBeTruthy()
  })

  it('offers no input box while it cannot answer', () => {
    // An input that takes a question and cannot answer it is worse than none:
    // somebody types the thing they most want to know and gets silence.
    const { container } = render(<AssistantPanel assistant={FINANCE} />)

    expect(container.querySelectorAll('input, textarea')).toHaveLength(0)
  })

  it('renders nothing once the real panel exists', () => {
    // P20 replaces this. Rendering both would show a founder two assistants.
    const { container } = render(
      <AssistantPanel assistant={{ ...FINANCE, available: true }} />,
    )

    expect(container.firstChild).toBeNull()
  })
})
