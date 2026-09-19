import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * The skip link lands somewhere, on every route.
 *
 * `app/layout.tsx` renders one "Skip to content" anchor for the whole app,
 * pointing at `#main`. For most of this product's life that id existed in
 * exactly two places — `AppShell` and the landing page — so the very first
 * control a keyboard or screen-reader user meets did nothing on **13 routes**:
 * the seven behind `AuthShell`, `/scan`, the OAuth callback, `/onboarding/agent`,
 * and (added the same week, by me) `/documents`, `/review-queue`, `/privacy` and
 * `/terms`.
 *
 * That is the shape of defect a comment cannot prevent: every one of those pages
 * was written correctly by its own lights, and nothing connected them to the
 * anchor in the root layout. So the rule is mechanical now.
 *
 * **Static rather than rendered**, because the property is about every route
 * including ones that need a session, a provider callback or an error boundary
 * — and mounting all of those to check one attribute would be a far more
 * fragile test than reading the files.
 */

const ROOT = process.cwd()

function tsxFilesUnder(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === '.next') continue
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) out.push(...tsxFilesUnder(path))
    else if (entry.endsWith('.tsx')) out.push(path)
  }
  return out
}

/** Every `<main` in the file, with the id attribute it carries (if any). */
function mainTags(source: string): string[] {
  return source.match(/<main[\s>][^>]*/g) ?? []
}

const files = [...tsxFilesUnder(join(ROOT, 'app')), ...tsxFilesUnder(join(ROOT, 'components'))]

describe('the skip link target', () => {
  it('finds the files to check', () => {
    // Guards the guard: a moved directory would otherwise make this vacuous.
    expect(files.length).toBeGreaterThan(20)
  })

  it('is on every <main> in the app', () => {
    const offenders: string[] = []
    for (const file of files) {
      for (const tag of mainTags(readFileSync(file, 'utf8'))) {
        if (!tag.includes('id="main"')) offenders.push(file.replace(`${ROOT}/`, ''))
      }
    }

    expect(
      offenders,
      `these render a <main> the skip link cannot reach: ${offenders.join(', ')}`,
    ).toEqual([])
  })

  it('can actually take focus, not just scroll into view', () => {
    // `id` alone moves the *viewport* and, in Safari and Firefox, leaves focus
    // where it was — so the next Tab returns to the navigation the user just
    // asked to skip, and a screen reader keeps reading from the old position.
    // The link appears to work and does not. `tabIndex={-1}` makes the target
    // programmatically focusable without putting it in the tab order.
    const offenders: string[] = []
    for (const file of files) {
      for (const tag of mainTags(readFileSync(file, 'utf8'))) {
        if (tag.includes('id="main"') && !tag.includes('tabIndex={-1}')) {
          offenders.push(file.replace(`${ROOT}/`, ''))
        }
      }
    }

    expect(
      offenders,
      `the skip link would scroll to these without moving focus: ${offenders.join(', ')}`,
    ).toEqual([])
  })

  it('is what the root layout actually points at', () => {
    // The other half of the pair. Renaming the anchor's target would leave
    // every assertion above passing and the link still broken.
    const layout = readFileSync(join(ROOT, 'app', 'layout.tsx'), 'utf8')
    expect(layout).toContain('href="#main"')
    expect(layout).toContain('Skip to content')
  })
})
