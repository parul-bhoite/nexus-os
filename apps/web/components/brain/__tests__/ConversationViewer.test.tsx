import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ConversationViewer } from '@/components/brain/ConversationViewer'
import type { Turn } from '@/lib/agent-onboarding-client'

const TURNS: Turn[] = [
  { role: 'agent', text: 'Who actually buys from you?', target: null, scope: null },
  {
    role: 'user',
    text: 'Mostly contractors and facilities teams.',
    target: 'brain.target_customers',
    scope: 2,
  },
  { role: 'agent', text: 'What would make the next year a success?', target: null, scope: null },
  { role: 'user', text: 'Growing recurring revenue.', target: 'brain.goals', scope: 2 },
]

describe('ConversationViewer', () => {
  it('shows a real empty state, not a blank log, when there are no turns', () => {
    render(<ConversationViewer turns={[]} />)
    expect(screen.getByText('No onboarding conversation on record')).toBeVisible()
    expect(screen.queryByRole('log')).not.toBeInTheDocument()
  })

  it('renders every turn in order inside a log, agent and user distinguishable', () => {
    render(<ConversationViewer turns={TURNS} />)
    const log = screen.getByRole('log', { name: /onboarding conversation transcript/i })
    const bubbles = within(log).getAllByText(/./, { selector: 'p:first-of-type' })
    expect(bubbles.map((b) => b.textContent)).toEqual([
      'Who actually buys from you?',
      'Mostly contractors and facilities teams.',
      'What would make the next year a success?',
      'Growing recurring revenue.',
    ])
    expect(within(log).getByText('brain.target_customers · L2')).toBeVisible()
  })

  it('filters the transcript by search text, client-side', () => {
    render(<ConversationViewer turns={TURNS} />)
    fireEvent.change(screen.getByRole('searchbox', { name: /search the onboarding conversation/i }), {
      target: { value: 'recurring revenue' },
    })
    const log = screen.getByRole('log')
    expect(within(log).getByText(/Growing/)).toBeVisible()
    expect(within(log).queryByText('Mostly contractors and facilities teams.')).not.toBeInTheDocument()
  })

  it('says so, and offers to clear the search, when nothing matches', () => {
    render(<ConversationViewer turns={TURNS} />)
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'zzz-not-present' } })
    expect(screen.getByText('Nothing matches that search')).toBeVisible()
  })

  it('highlights the matching text within a bubble rather than only filtering', () => {
    render(<ConversationViewer turns={TURNS} />)
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'contractors' } })
    const mark = screen.getByText('contractors', { selector: 'mark' })
    expect(mark).toBeVisible()
  })
})
