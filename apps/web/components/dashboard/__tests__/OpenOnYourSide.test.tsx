import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { OpenOnYourSide } from '@/components/dashboard/OpenOnYourSide'
import type { OpenQuestions } from '@/lib/dashboard-client'

/**
 * The questions region — `doc/14` step 5.
 *
 * The split is the API's and is asserted in `test_open_questions.py`. What only
 * the screen can get wrong:
 *
 * - **Over-claiming.** The region must not imply an answer unlocks anything.
 *   Every fact-consuming tile also needs a source, so the honest verb is
 *   "changes", and "unlock" appearing here would undo the correction the whole
 *   module exists for.
 * - **Burying the one that matters.** Twenty-eight rows of questions nobody can
 *   act on would hide the single one that moves a live figure.
 * - **A region with nothing in it.** Unlike the brief there is no absence to
 *   distinguish, so nothing open means no region rather than an empty card.
 */

function questions(overrides: Partial<OpenQuestions> = {}): OpenQuestions {
  return {
    changes_a_figure: [
      {
        key: 'arabic_in_scope',
        department: 'marketing',
        prompt: 'Is Arabic-language content in scope this year?',
        why: 'Whether the Arabic-language gap is reported as an opportunity or suppressed as out of scope.',
        consumed_by: 'marketing.seo_gaps',
        consumer_name: 'SEO Intelligence',
      },
    ],
    waiting_on_us: 28,
    total: 29,
    ...overrides,
  }
}

describe('what the region claims', () => {
  it('says an answer changes a figure, never that it unlocks one', () => {
    const { container } = render(<OpenOnYourSide questions={questions()} />)

    expect(screen.getByText(/would change a figure on this page/)).toBeTruthy()
    // The design's original claim. Zero capabilities are unlockable by
    // answering, so the word must not reappear here.
    expect(container.textContent?.toLowerCase()).not.toContain('unlock')
  })

  it('names the capability that reads each answer', () => {
    render(<OpenOnYourSide questions={questions()} />)

    // A question whose consumer cannot be named is a form field (doc 06), and
    // this is where that shows.
    expect(screen.getByText('SEO Intelligence')).toBeTruthy()
  })

  it('uses the bank’s own prompt and reason rather than a rewrite', () => {
    const one = questions().changes_a_figure[0]
    render(<OpenOnYourSide questions={questions()} />)

    expect(screen.getByText(one.prompt)).toBeTruthy()
    expect(screen.getByText(one.why)).toBeTruthy()
  })

  it('says plainly that the rest change nothing yet, and why', () => {
    render(<OpenOnYourSide questions={questions()} />)

    expect(screen.getByText(/28 more questions/)).toBeTruthy()
    expect(screen.getByText(/the capabilities that read\s+them are not built/)).toBeTruthy()
  })
})

describe('the shapes a real workspace produces', () => {
  it('counts the rest without listing them', () => {
    const { container } = render(<OpenOnYourSide questions={questions()} />)

    // One row, not twenty-nine. A long list buries the only line somebody can
    // act on today.
    expect(container.querySelectorAll('li')).toHaveLength(1)
  })

  it('renders the count alone when nothing moves a figure', () => {
    render(<OpenOnYourSide questions={questions({ changes_a_figure: [], total: 28 })} />)

    expect(screen.queryByText(/would change a figure/)).toBeNull()
    expect(screen.getByText(/28 more questions/)).toBeTruthy()
  })

  it('renders nothing at all when every question is answered', () => {
    const { container } = render(
      <OpenOnYourSide questions={questions({ changes_a_figure: [], waiting_on_us: 0, total: 0 })} />,
    )

    // No absence to distinguish here, unlike the brief: an empty list means
    // every question has an answer, which needs no sentence.
    expect(container.innerHTML).toBe('')
  })
})
