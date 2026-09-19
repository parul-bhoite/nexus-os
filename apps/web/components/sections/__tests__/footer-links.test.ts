import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { footer } from '@/lib/content'

/**
 * Every footer link goes somewhere.
 *
 * This guard exists because the footer once carried **seven** `href="#"`
 * controls — About, Design partners, Careers, Contact, Security, Privacy and
 * Terms — that looked like navigation and scrolled to the top. They were removed
 * rather than left pointing at a placeholder, and the comment in `content.ts`
 * recorded why Privacy and Terms mattered most: *a link to a privacy policy that
 * does not exist implies a document a customer could rely on.*
 *
 * Those two are back now that the pages exist (H11), which is exactly the moment
 * to make the rule mechanical. Nothing checked it before; the discipline lived
 * in a comment, and a comment is not a guard.
 */

const APP = join(process.cwd(), 'app')

/** `/privacy` → `app/privacy/page.tsx`. Route groups and dynamic segments would
 *  need more than this; the footer has neither, and a checker that silently
 *  handled cases the data cannot contain would be harder to trust. */
function pageExists(href: string): boolean {
  return existsSync(join(APP, href.replace(/^\//, ''), 'page.tsx'))
}

type Link = { label: string; href: string }

// `as const` types each column's `links` as its own tuple, so `flatMap` cannot
// infer one element type across them. Widened here rather than by loosening
// `content.ts`, whose literal types are useful to the components.
const links: Link[] = footer.columns.flatMap((column) => [...column.links] as Link[])

describe('footer links', () => {
  it('has links to check', () => {
    // Guards the guard: a refactor that renamed `columns` would otherwise make
    // every assertion below vacuously true.
    expect(links.length).toBeGreaterThan(5)
  })

  it('points at no placeholder', () => {
    const dead = links.filter((l) => l.href === '#' || l.href === '')
    expect(dead, `${dead.map((l) => l.label).join(', ')} go nowhere`).toEqual([])
  })

  it('links only to pages that exist on disk', () => {
    const routes = links.filter((l) => l.href.startsWith('/'))
    const missing = routes.filter((l) => !pageExists(l.href))

    expect(
      missing,
      `footer promises ${missing.map((l) => `${l.label} (${l.href})`).join(', ')} — no such page`,
    ).toEqual([])
  })

  it('still offers Privacy and Terms, which signups need', () => {
    // Named specifically rather than counted: these are the two whose absence
    // was a live exposure while accounts could already be created.
    const hrefs = links.map((l) => l.href)
    expect(hrefs).toContain('/privacy')
    expect(hrefs).toContain('/terms')
  })
})
