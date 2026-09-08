import { describe, expect, it } from 'vitest'

import { messageFrom } from '@/lib/api-error'

/**
 * `detail` is `unknown` at the boundary and arrives in three shapes. The third
 * one — this API's own structured refusals — was falling through to the
 * fallback, so every deliberately-worded error in onboarding rendered as
 * "The request failed (502)." while the server had sent a real sentence.
 */
describe('messageFrom', () => {
  it('reads a plain string detail', () => {
    expect(messageFrom({ detail: 'No onboarding in progress.' }, 'fallback')).toBe(
      'No onboarding in progress.',
    )
  })

  it('reads the message out of a structured refusal', () => {
    expect(
      messageFrom(
        { detail: { error: 'skill_failed', message: 'The assistant could not answer.' } },
        'The request failed (502).',
      ),
    ).toBe('The assistant could not answer.')
  })

  it('reads the first message of a FastAPI validation error', () => {
    expect(
      messageFrom({ detail: [{ msg: 'String should have at least 1 character' }] }, 'fallback'),
    ).toBe('String should have at least 1 character')
  })

  it('falls back rather than rendering an object', () => {
    // The crash this file exists for: an object reached React as a child.
    expect(messageFrom({ detail: { error: 'skill_failed' } }, 'fallback')).toBe('fallback')
    expect(messageFrom({ detail: {} }, 'fallback')).toBe('fallback')
    expect(messageFrom(null, 'fallback')).toBe('fallback')
  })
})
