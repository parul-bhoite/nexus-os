import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RegisterCompanyForm } from '@/components/auth/RegisterCompanyForm'
import * as client from '@/lib/auth-client'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}))

vi.mock('@/lib/auth-client', async (importOriginal) => {
  const actual = await importOriginal<typeof client>()
  return { ...actual, fetchDepartments: vi.fn(), registerCompany: vi.fn(), requestToJoin: vi.fn() }
})

const mocked = vi.mocked(client)

const CHOICES: client.DepartmentChoice[] = [
  { value: 'sales', label: 'Sales' },
  { value: 'hr', label: 'People' },
  { value: 'executive', label: 'Chief of Staff' },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('RegisterCompanyForm department', () => {
  it('offers the served labels, never a title-cased key', async () => {
    // Finding F13: `hr` rendered as "Hr" on one surface and "People" on
    // another, because each surface capitalised the enum itself. The labels are
    // served, so the browser never has to guess.
    mocked.fetchDepartments.mockResolvedValue(CHOICES)

    render(<RegisterCompanyForm />)

    const select = await screen.findByLabelText('Department')
    expect(select.tagName).toBe('SELECT')
    // Shown by label, submitted by key — both halves matter now.
    expect(screen.getByRole('option', { name: 'People' })).toHaveValue('hr')
    expect(screen.queryByRole('option', { name: 'Hr' })).not.toBeInTheDocument()
    // Optional, so "nothing chosen" has to be expressible.
    expect(screen.getByRole('option', { name: 'Select…' })).toHaveValue('')
  })

  it('submits the key, because the server narrows the catalogue by it', async () => {
    // `askable_fields(department)` matches this against the `Department` enum
    // to decide which fields the interview may target. Submitting "People"
    // would not match, and the agent would be offered every department's
    // fields — which is the 26%-wrong-department finding it exists to fix.
    // The greeting still reads "in People"; `_viewer` resolves it there.
    mocked.fetchDepartments.mockResolvedValue(CHOICES)
    mocked.registerCompany.mockResolvedValue({
      workspace_id: 'w1',
      domain: 'xebia.com',
      domain_verified: false,
    })

    render(<RegisterCompanyForm />)
    const select = await screen.findByLabelText('Department')

    fireEvent.change(screen.getByLabelText('Company name'), { target: { value: 'Xebia' } })
    fireEvent.change(screen.getByLabelText('Website'), { target: { value: 'xebia.com' } })
    // Chosen by its visible label; what leaves is the key behind it.
    fireEvent.change(select, { target: { value: 'hr' } })
    fireEvent.click(screen.getByRole('button', { name: /create company/i }))

    await waitFor(() => expect(mocked.registerCompany).toHaveBeenCalledOnce())
    // Two arguments: the details, then the caller's options.
    expect(mocked.registerCompany).toHaveBeenCalledWith(
      expect.objectContaining({ department: 'hr' }),
      expect.anything(),
    )
  })

  it('still lets the company be created when the list cannot be loaded', async () => {
    // Department is optional. Losing an optional field beats losing the company,
    // so a failed catalogue fetch disables one select and blocks nothing.
    mocked.fetchDepartments.mockRejectedValue(new Error('offline'))
    mocked.registerCompany.mockResolvedValue({
      workspace_id: 'w1',
      domain: 'xebia.com',
      domain_verified: false,
    })

    render(<RegisterCompanyForm />)

    const select = await screen.findByLabelText('Department')
    await waitFor(() => expect(select).toBeDisabled())
    expect(screen.getByRole('option', { name: /unavailable/i })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Company name'), { target: { value: 'Xebia' } })
    fireEvent.change(screen.getByLabelText('Website'), { target: { value: 'xebia.com' } })
    fireEvent.click(screen.getByRole('button', { name: /create company/i }))

    await waitFor(() => expect(mocked.registerCompany).toHaveBeenCalledOnce())
    expect(mocked.registerCompany).toHaveBeenCalledWith(
      expect.objectContaining({ department: null }),
      expect.anything(),
    )
  })
})
