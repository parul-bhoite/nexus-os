import { expect, test, type Page } from '@playwright/test'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

/**
 * The founder's journey, end to end, in a browser.
 *
 * Land → sign up → verify by email → register the company → answer the five
 * company questions → select departments → answer your own department's block
 * → upload a document → reach the dashboard.
 *
 * **Written before the Dockerfiles** (`doc/12` P9), so "it works deployed"
 * means this passes against the deployment rather than "the container started".
 *
 * **One test, not nine.** Each step depends on the state the last one left, and
 * splitting them into independent tests would mean either re-running the whole
 * prefix nine times or sharing state between tests that claim to be
 * independent. The journey *is* the unit under test: a product where every step
 * works and the sequence does not is a broken product.
 *
 * The verification token is read from the mail sink, which is what the file
 * mailer is for (ADR 0011's pattern — no provider needed to prove the chain).
 * Reading the database instead would skip the delivery this step exists to
 * prove.
 */

const MAIL_DIR = process.env.NEXUS_E2E_MAIL_DIR ?? '../../.mail'
/** Set against the composed stack, where mail is really sent. Unset locally. */
const MAIL_API = process.env.NEXUS_E2E_MAIL_API
const PASSWORD = 'correct horse battery staple 9'

const stamp = Date.now()
const domain = `journey-${stamp}.om`
const email = `founder+${stamp}@${domain}`

/**
 * The newest verification link in whatever the stack is actually sending to.
 *
 * Two sinks, because the stack has two shapes. Against the **composed
 * deployment** mail is genuinely sent over SMTP to Mailpit, and is read back
 * through its API — `NEXUS_ENV=production` forbids the file mailer (finding
 * #24), so there is no `.eml` on disk to read and that refusal is correct.
 * Against a **dev server** the file mailer is in use and the `.eml` is right
 * there.
 *
 * Reading the token from the database would be simpler and would skip the
 * delivery this step exists to prove.
 */
async function tokenFromMailApi(base: string, since: number): Promise<string> {
  const deadline = Date.now() + 30_000
  while (Date.now() < deadline) {
    const list = await fetch(`${base}/api/v1/messages?limit=20`).catch(() => null)
    if (list?.ok) {
      const { messages = [] } = (await list.json()) as {
        messages?: { ID: string; Created: string }[]
      }
      for (const message of messages) {
        if (Date.parse(message.Created) < since - 5_000) continue
        // The source, not the rendered body: Mailpit will happily give HTML,
        // and the link is easier to find in the raw part than in markup.
        const raw = await fetch(`${base}/api/v1/message/${message.ID}`).catch(() => null)
        if (!raw?.ok) continue
        const body = (await raw.json()) as { Text?: string; HTML?: string }
        const match = `${body.Text ?? ''}${body.HTML ?? ''}`.match(/token=([A-Za-z0-9_\-.]{16,})/)
        if (match) return match[1]
      }
    }
    await new Promise((r) => setTimeout(r, 1_000))
  }
  throw new Error(`No verification email reached ${base} within 30s`)
}

/** The file-mailer sink, decoded as mail rather than read as text: it writes
 *  quoted-printable, so a raw read soft-wraps the token at column 76 and every
 *  regex over it silently captures half a token. */
function verificationToken(since: number): string {
  const deadline = Date.now() + 20_000
  while (Date.now() < deadline) {
    const files = readdirSync(MAIL_DIR)
      .filter((f) => f.endsWith('.eml'))
      .map((f) => ({ f, at: statSync(join(MAIL_DIR, f)).mtimeMs }))
      .filter((x) => x.at > since)
      .sort((a, b) => b.at - a.at)

    for (const { f } of files) {
      const raw = readFileSync(join(MAIL_DIR, f), 'utf8')
      const unwrapped = raw.replace(/=\r?\n/g, '').replace(/=3D/g, '=')
      const match = unwrapped.match(/token=([A-Za-z0-9_\-.]{16,})/)
      if (match) return match[1]
    }
  }
  throw new Error('No verification email arrived within 20s')
}

async function fill(page: Page, label: RegExp | string, value: string) {
  await page.getByLabel(label).fill(value)
}

test('a founder can go from the landing page to their dashboard', async ({ page }) => {
  const before = Date.now()

  await test.step('the landing page loads and offers a way in', async () => {
    await page.goto('/')
    await expect(page).toHaveTitle(/NEXUS/i)
  })

  await test.step('sign up', async () => {
    await page.goto('/register')
    await fill(page, /work email/i, email)
    await fill(page, /^password/i, PASSWORD)
    await page.getByRole('button', { name: /create|sign up|get started/i }).click()
    await expect(page.getByText(/check your (email|inbox)|verify/i)).toBeVisible()
  })

  await test.step('verify by email, using the link that was actually sent', async () => {
    const token = MAIL_API
      ? await tokenFromMailApi(MAIL_API, before)
      : verificationToken(before)
    await page.goto(`/verify-email?token=${token}`)
    // `.first()`: the confirmation page names the state in a heading *and* in
    // the sentence below it, which is good copy and a strict-mode violation.
    // Asserting the first match keeps the check about "did verification
    // succeed" rather than about how many times the page says so.
    await expect(page.getByText(/verified|confirmed|signed in/i).first()).toBeVisible()
  })

  await test.step('sign in', async () => {
    await page.goto('/login')
    await fill(page, /work email/i, email)
    await fill(page, /^password/i, PASSWORD)
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page).not.toHaveURL(/\/login/)

    // **The reason the reverse proxy exists**, asserted where a session
    // actually exists. It was a separate curl step against a *failed* login —
    // which sets no cookies at all, correctly, so the check could only ever
    // pass by accident. A cookie assertion needs a cookie.
    //
    // `Secure` is what makes the proxy load-bearing rather than decorative: a
    // session cookie marked secure is not sent over plain HTTP, so a stack
    // serving the app without TLS would pass every other step here and still be
    // undeployable. `HttpOnly` keeps the session out of reach of any script
    // that finds its way onto the page.
    if ((process.env.NEXUS_E2E_BASE_URL ?? '').startsWith('https://')) {
      const cookies = await page.context().cookies()
      const session = cookies.find((c) => c.name === 'nexus_session')
      expect(session, 'the sign-in set no session cookie').toBeTruthy()
      expect(session!.secure, 'nexus_session must be Secure').toBe(true)
      expect(session!.httpOnly, 'nexus_session must be HttpOnly').toBe(true)

      const csrf = cookies.find((c) => c.name === 'nexus_csrf')
      expect(csrf, 'the sign-in set no CSRF cookie').toBeTruthy()
      expect(csrf!.secure, 'nexus_csrf must be Secure').toBe(true)
      // Deliberately *not* HttpOnly: the browser has to read it to echo it back
      // in the header, which is the whole double-submit mechanism.
    }
  })

  await test.step('register the company', async () => {
    await page.goto('/register-company')
    await fill(page, /company name/i, `Journey Trading ${stamp}`)
    await fill(page, /website/i, `https://${domain}`)
    await page.getByRole('button', { name: /create|register|continue/i }).click()
    await expect(page).not.toHaveURL(/register-company/)
  })

  await test.step('the five company questions, one of them skipped', async () => {
    await page.goto('/onboarding')

    const boxes = page.getByRole('textbox')
    await expect(boxes.first()).toBeVisible()
    const count = await boxes.count()
    expect(count).toBe(5)

    for (let i = 0; i < count; i += 1) await boxes.nth(i).fill('A real answer from the journey')

    // "Not sure yet" appears only where the question has a stated assumption to
    // fall back on, so ticking one exercises the mechanism rather than a
    // checkbox. Asserted rather than skipped-if-absent: a step that quietly
    // does nothing when its control is missing is a step that cannot fail.
    const unsure = page.getByRole('checkbox')
    await expect(unsure.first()).toBeVisible()
    await unsure.first().check()

    await page.getByRole('button', { name: /continue|save|next/i }).first().click()
  })

  await test.step('select departments', async () => {
    // Waiting for the *next* stage's control, not a timeout. The stage advances
    // on a round trip, and asserting on whatever is on screen a moment later is
    // how this suite would become flaky.
    const finance = page.getByLabel(/^finance$/i)
    await expect(finance).toBeVisible()

    await finance.check()
    await page.getByLabel(/^sales$/i).check()
    await page.getByRole('button', { name: /continue|save|next|finish/i }).first().click()
  })

  await test.step("answer your own department's block", async () => {
    await page.goto('/onboarding/finance')

    // `.all()` resolves immediately against whatever is in the DOM *now* — it
    // does not auto-wait the way a locator action does. Against a real database
    // this page is still "Loading…" for a second or two, so collecting the
    // boxes without waiting first is how this step reads zero of them.
    const boxes = page.getByRole('textbox')
    await expect(boxes.first()).toBeVisible()
    expect(await boxes.count()).toBeGreaterThan(0)

    await boxes.first().fill('30 days')
    await page.getByRole('button', { name: /save|propose/i }).click()
    await expect(page.getByText(/^answered$/i).first()).toBeVisible()
  })

  await test.step('upload a document', async () => {
    await page.goto('/onboarding/documents')
    await page.getByRole('checkbox').first().check()
    await page.setInputFiles('input[type="file"]', {
      name: 'prices.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('Item,Price\nWidget,12.500\nGadget,8.250\n'),
    })
    // Scoped to the row for this file. Bare `getByText('indexed')` matches the
    // badge, the summary line and the explanatory copy — three elements, and a
    // strict-mode violation rather than an assertion about the upload.
    const row = page.locator('li', { hasText: 'prices.csv' }).first()
    await expect(row.getByText('indexed', { exact: true })).toBeVisible()
  })

  await test.step('reach the dashboard, which is honest about being empty', async () => {
    await page.goto('/dashboard')
    // Doc 05 §1's shell is not built, and the page says so rather than showing
    // a score of zero. Asserting the honesty is asserting I10.
    await expect(page.getByText(/none of them is built|planned/i).first()).toBeVisible()
  })
})
