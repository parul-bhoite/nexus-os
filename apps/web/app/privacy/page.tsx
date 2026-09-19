import type { Metadata } from 'next'
import { Fact, LegalPage, Pending, Section } from '@/components/legal/LegalPage'

export const metadata: Metadata = {
  title: 'Privacy',
  description: 'What NEXUS OS stores, how long it keeps it, and what leaves the system.',
}

/**
 * H11, the privacy half.
 *
 * Every number and every claim below was read out of the code on 19 September
 * 2026 and carries the file that makes it true, so a reader can check rather
 * than trust. Where the software's behaviour is imperfect — the rolling session
 * with no absolute cap, the absent retention policy for account data — it is
 * stated rather than smoothed over, because a privacy page that describes a
 * better system than the one running is the worst version of this document.
 */
export default function PrivacyPage() {
  return (
    <LegalPage
      kicker="Privacy"
      title="What NEXUS holds, and what leaves"
      lede="Written from the code rather than from a template. Each statement names the file it came from."
      missing={
        <>
          <Pending
            what="Who the data controller is"
            needs="The legal entity, its place of establishment, and a registered address. None of these exist in the codebase or in any document here."
          />
          <Pending
            what="The PDPL position"
            needs="Oman's Personal Data Protection Law applies to this product's intended market. Whether NEXUS is controller or processor for workspace content, and what registration or DPA obligations follow, is a legal question nobody has answered."
          />
          <Pending
            what="How to make a data request, and to whom"
            needs="There is no contact address, no route in the product, and no stated response time for access, correction or erasure requests."
          />
          <Pending
            what="How long account data is kept after you leave"
            needs="The code defines retention for scans, sessions, download links and rate-limit counters. It defines none for your account, your workspace, or the documents in it."
          />
        </>
      }
    >
      <Section title="What is stored about you">
        <p>
          Creating an account stores your work email and a hash of your password. A name and a
          phone number are optional and stored as given. Joining a workspace stores your role and
          the departments you hold, which is what every permission check reads.
        </p>
        <p>
          Using the product stores what you tell it: the answers from the setup interview, the
          documents you upload and the passages extracted from them, and an audit record of
          consequential actions such as creating a workspace or issuing an invitation.
        </p>
      </Section>

      <Section title="How long things are kept">
        <ul className="flex flex-col divide-y divide-bone-200">
          <Fact source="app/config.py — session_max_age_seconds">
            <strong>Sessions last 12 hours</strong>, and the window extends while you are active.
            There is no absolute cap on top of that, so a session in continuous use does not expire
            on a schedule. That is a known open item, not an oversight we are hiding.
          </Fact>
          <Fact source="migration 0037, app/jobs/expiry.py">
            <strong>Website scan results are deleted after seven days.</strong> Deleting one
            yourself marks it immediately and it is removed for good within a day.
          </Fact>
          <Fact source="app/routes/documents.py — DOWNLOAD_TTL_SECONDS">
            <strong>Download links expire after five minutes.</strong> Holding the link is not
            authorisation — it is checked once, against the person who uploaded the file.
          </Fact>
          <Fact source="app/connectors/rate_limit.py — hash_bucket_key">
            <strong>Rate limiting counts you without naming you.</strong> Whatever identifies a
            caller is stored as a keyed hash, so the table is not a plaintext list of addresses.
          </Fact>
          <Fact source="no implementation exists">
            <strong>Account and workspace data has no defined retention.</strong> It stays until
            somebody deletes it, and there is no way to ask the product to do that yet.
          </Fact>
        </ul>
      </Section>

      <Section title="What leaves the system">
        <ul className="flex flex-col divide-y divide-bone-200">
          <Fact source="app/ai/ — Anthropic provider">
            <strong>Text you give NEXUS is sent to Anthropic</strong> when the setup interview runs
            and when a figure is narrated. That includes what you type in the interview and the
            contents of documents used to build your Company Brain.
          </Fact>
          <Fact source="app/embeddings/fastembed_provider.py">
            <strong>Embeddings are computed locally.</strong> Document text is not sent anywhere to
            be embedded — a separate decision from the one above, and the reason the two are listed
            apart.
          </Fact>
          <Fact source="ADR 0008 — Neon, us-east-2">
            <strong>The database is hosted by Neon, in the United States.</strong> If your data must
            stay in a particular jurisdiction, this is the line to raise with us before signing up.
          </Fact>
          <Fact source="app/mail.py">
            <strong>Email is sent through an SMTP provider</strong> for verification and
            invitations. The address and the link are in the message.
          </Fact>
        </ul>
      </Section>

      <Section title="Who inside your workspace can see what">
        <p>
          Content carries a sensitivity from L1 to L5 and is filtered by the database itself rather
          than by the screen, so a permission mistake in the interface cannot widen what a query
          returns.
        </p>
        <p>
          Uploaded documents are withheld by default. Anything read as personal or financial — a
          salary line, a bank account number — is held for a person to place, however confident the
          classifier was. Until somebody places it, it is readable only by whoever uploaded it.
        </p>
      </Section>

      <Section title="Scanning a website">
        <p>
          The gap analysis can be run without an account, on any address. It reads one page,
          respects that site&apos;s <code className="font-mono text-2xs">robots.txt</code>, and keeps
          what it measured for seven days so the result can be reopened.
        </p>
        <p>
          <strong>The subject of that data may not be the person who asked for it</strong> — anyone
          can type any domain. So the record is keyed to the domain rather than to a visitor, holds
          no page content, and anyone holding the result&apos;s link can delete it.
        </p>
      </Section>
    </LegalPage>
  )
}
