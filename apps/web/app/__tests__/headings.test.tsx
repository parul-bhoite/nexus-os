import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Every signed-in page names itself.
 *
 * **A regression this caught after it had shipped.** `/settings` and `/account`
 * each drew their own header, `<h1>` and standfirst; moving them into the shell
 * (`doc/14` step 1) took the chrome and the heading together, and the pages went
 * out with six `h2`s and no name. Nothing failed — `tsc`, lint and every
 * component test stayed green, because a missing heading is not a broken one.
 *
 * A screen reader announces the `h1` as the name of where somebody is. Without
 * it, three different pages inside one shell are indistinguishable from each
 * other by anything but their content.
 *
 * Asserted against the source rather than by rendering: these are server
 * components whose children fetch, and standing that up would test Next rather
 * than the thing at risk. The failure mode is an omission, and an omission is
 * exactly what a grep over the file catches and a render might not.
 *
 * **At least one, not exactly one — and the difference is not laziness.** These
 * pages render mutually exclusive states: `DirectorPage` has a heading for the
 * director, one for the entity chooser and one for an unreachable API, and only
 * ever one of them is in the DOM. A static count cannot tell three branches with
 * a heading each from three headings on one screen, so "exactly one" would be
 * asserting something this file cannot see. That claim needs a render per state;
 * what a scan can honestly establish is that a page has not lost its name, which
 * is the regression that actually happened.
 */

const APP = join(process.cwd(), 'app')

/** Routes rendered inside `AppShell`, which is what strips their chrome. */
const IN_SHELL = ['dashboard', 'settings', 'account']

/**
 * The page's own source, plus any component it delegates its body to.
 *
 * The first cut of this grepped `page.tsx` alone and failed on the two pages
 * that hand everything to a client component — which is most of them, because a
 * server component cannot hold the fetch these pages need. Following one level
 * is what the paragraph above already promised and the implementation did not.
 */
function sourcesFor(file: string): string {
  const own = readFileSync(file, 'utf8')
  // `Array.from` rather than spreading the iterator: this file is type-checked
  // against the app's tsconfig, whose target does not permit iterating a
  // `RegExpStringIterator` directly.
  const delegated = Array.from(own.matchAll(/from '@\/components\/([^']+)'/g)).map((match) =>
    join(process.cwd(), 'components', `${match[1]}.tsx`),
  )
  return [own, ...delegated.map((path) => readFileSync(path, 'utf8'))].join('\n')
}

function pageFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) return pageFiles(path)
    return entry === 'page.tsx' ? [path] : []
  })
}

describe('every page inside the shell', () => {
  it('carries a name of its own', () => {
    const offenders: string[] = []

    for (const route of IN_SHELL) {
      for (const file of pageFiles(join(APP, route))) {
        // A page may delegate its heading to the one component it renders, so
        // the search follows that hop.
        if (!/<h1[\s>]/.test(sourcesFor(file))) {
          offenders.push(file.replace(APP, 'app'))
        }
      }
    }

    expect(offenders, 'a page with no h1 has no name for a screen reader').toEqual([])
  })

  it('does not draw its own logo or page frame', () => {
    // The other half of the same change. Three pages had each written their own
    // header and the three had already drifted — one linked "Workspace setup"
    // where another did not, so the same person saw different destinations
    // depending which page they were on.
    const offenders: string[] = []

    for (const route of IN_SHELL) {
      for (const file of pageFiles(join(APP, route))) {
        // Own source only here: the shell's own components legitimately draw a
        // logo, and following delegation would flag every page that reaches
        // them.
        const source = readFileSync(file, 'utf8')
        if (source.includes('<Logo') || source.includes('min-h-screen')) {
          offenders.push(file.replace(APP, 'app'))
        }
      }
    }

    expect(offenders, 'the shell owns the frame; a page drawing its own will double it').toEqual(
      [],
    )
  })
})
