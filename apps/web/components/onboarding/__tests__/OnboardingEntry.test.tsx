import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { OnboardingEntry } from '@/components/onboarding/OnboardingEntry'
import { AuthError } from '@/lib/auth-client'
import { fetchCompany } from '@/lib/settings-client'

/**
 * `OnboardingEntry`'s whole job is resuming at the right beat — company
 * details first, the conversation once a workspace exists (its own doc
 * comment explains why company creation stays a form rather than a chat
 * turn). `ConversationalOnboarding` is stubbed here: its own boot sequence
 * against the agent client is covered by `ConversationalOnboarding.test.tsx`,
 * and exercising it for real would duplicate those mocks for a test that is
 * really about routing.
 */

vi.mock('@/lib/settings-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/settings-client')>()
  return { ...actual, fetchCompany: vi.fn() }
})

vi.mock('@/components/onboarding/ConversationalOnboarding', () => ({
  ConversationalOnboarding: () => <div>the conversation</div>,
}))

beforeEach(() => {
  vi.mocked(fetchCompany).mockReset()
})

describe('OnboardingEntry resume', () => {
  it('resumes at company details when no workspace has been created yet', async () => {
    vi.mocked(fetchCompany).mockRejectedValue(new AuthError('no workspace selected', 403))

    render(<OnboardingEntry />)

    expect(await screen.findByText(/let.s start with your company/i)).toBeInTheDocument()
  })

  it('goes straight to the conversation once a workspace exists', async () => {
    vi.mocked(fetchCompany).mockResolvedValue({
      workspace_id: 'w1',
      name: 'Acme',
      domain: 'acme.om',
      website_url: 'https://acme.om',
      domain_verified: false,
      role: 'admin',
      may_administer: true,
    })

    render(<OnboardingEntry />)

    expect(await screen.findByText('the conversation')).toBeInTheDocument()
  })

  it('shows a retryable error on a real failure, rather than guessing which beat to show', async () => {
    vi.mocked(fetchCompany).mockRejectedValue(new AuthError('database unavailable', 500))

    render(<OnboardingEntry />)

    expect(await screen.findByText(/could not reach the account service/i)).toBeInTheDocument()
  })
})
