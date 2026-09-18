import { Nav } from '@/components/sections/Nav'
import { Hero } from '@/components/sections/Hero'
import { Problem } from '@/components/sections/Problem'
import { Loop } from '@/components/sections/Loop'
import { Brain } from '@/components/sections/Brain'
import { Directors } from '@/components/sections/Directors'
import { Pillars } from '@/components/sections/Pillars'
import { Moments } from '@/components/sections/Moments'
import { Trust } from '@/components/sections/Trust'
import { Compare } from '@/components/sections/Compare'
import { Pricing } from '@/components/sections/Pricing'
import { Faq } from '@/components/sections/Faq'
import { FinalCta } from '@/components/sections/FinalCta'
import { Footer } from '@/components/sections/Footer'
import { ScrollProgress } from '@/components/ui/ScrollProgress'
import { PauseOffscreen } from '@/components/motion/PauseOffscreen'
import { site, faq } from '@/lib/content'

/** FAQ structured data — the marketing site is SSR'd for exactly this reason. */
function StructuredData() {
  const data = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'SoftwareApplication',
        name: site.name,
        applicationCategory: 'BusinessApplication',
        description: site.description,
        operatingSystem: 'Web',
      },
      {
        '@type': 'FAQPage',
        mainEntity: faq.items.map((i) => ({
          '@type': 'Question',
          name: i.q,
          acceptedAnswer: { '@type': 'Answer', text: i.a },
        })),
      },
    ],
  }

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  )
}

export default function HomePage() {
  return (
    <>
      <StructuredData />
      <ScrollProgress />
      {/* Decorative loops stop in sections that are off screen. */}
      <PauseOffscreen />
      <Nav />
      <main id="main">
        <Hero />
        <Problem />
        <Loop />
        <Brain />
        <Directors />
        <Pillars />
        <Moments />
        <Trust />
        <Compare />
        <Pricing />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </>
  )
}
