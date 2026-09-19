import type { Metadata } from 'next'
import { Fact, LegalPage, Pending, Section } from '@/components/legal/LegalPage'

export const metadata: Metadata = {
  title: 'Terms',
  description: 'What NEXUS OS does, what it refuses to do, and what is still undecided.',
}

/**
 * H11, the terms half — and the more incomplete of the two.
 *
 * A privacy page can be most of a real document by describing behaviour
 * accurately. Terms cannot: liability, warranty and governing law are the
 * substance, and none of them is a fact about the software. So this page states
 * what the product actually does and is candid that the contract part is
 * missing, rather than reaching for the clauses every template supplies.
 */
export default function TermsPage() {
  return (
    <LegalPage
      kicker="Terms"
      title="What the product does, and what is not settled"
      lede="The behaviour below is real and checkable. The parts that make terms a contract are not written."
      missing={
        <>
          <Pending
            what="Who you would be contracting with"
            needs="No legal entity is named anywhere in this product or its documents."
          />
          <Pending
            what="Governing law and jurisdiction"
            needs="Undecided. The product is built for Oman and the wider GCC, which is a market choice rather than a legal one."
          />
          <Pending
            what="Liability, warranty and indemnity"
            needs="Absent. Every template offers these; none of them would be a statement about this software, so none is here."
          />
          <Pending
            what="Availability, support and termination"
            needs="There is no uptime commitment, no support undertaking, and no stated process for ending an account or getting your data out."
          />
          <Pending
            what="Pricing and payment"
            needs="The landing page shows pricing. Nothing in the product charges anybody, and no billing terms exist."
          />
        </>
      }
    >
      <Section title="What the product undertakes to do">
        <p>
          One commitment is architectural rather than contractual, and it is the reason most of this
          product is shaped the way it is: <strong>every figure shown is fetched or computed</strong>
          , never generated. Where a number cannot be produced honestly, the product says so and
          names what is missing instead of estimating.
        </p>
        <ul className="flex flex-col divide-y divide-bone-200">
          <Fact source="app/documents/classify.py">
            A document is not readable by your workspace the moment it arrives. It is placed only if
            it can be placed safely; anything personal or financial waits for a person regardless of
            how confident the classifier was.
          </Fact>
          <Fact source="app/ai/ — UnavailableProvider">
            With no language model configured the product still runs and refuses the features that
            need one. It does not fall back to invented content.
          </Fact>
          <Fact source="app/domain/registry.py, /dashboard">
            Capabilities that are not built are shown as not built, counted in public on your own
            dashboard, rather than presented as empty results.
          </Fact>
        </ul>
      </Section>

      <Section title="What you warrant when you upload">
        <p>
          The wording you accept at upload time is served by the API and recorded with its version,
          so what you agreed to is a question about the text in force that day rather than about
          this page:
        </p>
        <blockquote className="border-l-2 border-bone-400 pl-4 text-[0.95rem] italic leading-relaxed text-ink-600">
          I warrant that this workspace has the right to use and index this document, and that doing
          so breaches no confidentiality obligation or third-party right.
        </blockquote>
      </Section>

      <Section title="Using the website scan">
        <p>
          The scan reads a single page of whatever address is entered. It honours that
          site&apos;s <code className="font-mono text-2xs">robots.txt</code>, refuses addresses that
          resolve to private networks, and is rate limited per address, per domain and overall.
        </p>
        <p>
          <strong>It does not verify that you own the domain you type</strong>, which is a real
          limitation and is why the result holds no page content, is keyed to the domain rather than
          to you, expires in seven days, and can be deleted by anyone holding its link.
        </p>
      </Section>

      <Section title="What the product is today">
        <p>
          NEXUS OS is in active development. Of the capabilities it describes, a minority produce a
          figure today and most are not built — the dashboard states the split for your own
          workspace rather than leaving you to discover it.
        </p>
        <p>
          Figures in marketing illustrations are labelled <em>Illustrative</em> and are not measured
          results from any customer.
        </p>
      </Section>
    </LegalPage>
  )
}
