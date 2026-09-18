import { Logo } from '@/components/ui/Logo'
import { footer, site } from '@/lib/content'

export function Footer() {
  return (
    <footer className="border-t border-bone-200 bg-bone-50">
      <div className="shell-full py-16">
        <div className="grid gap-12 lg:grid-cols-[1.4fr_2fr]">
          <div>
            <Logo />
            <p className="mt-5 max-w-sm text-pretty text-sm leading-relaxed text-ink-500">
              {footer.blurb}
            </p>
            <p className="mt-6 inline-flex items-center gap-2 rounded-full border border-bone-300 bg-white px-3 py-1.5 font-mono text-2xs uppercase tracking-[0.14em] text-ink-500">
              <span className="h-1.5 w-1.5 rounded-full bg-gold-500" />
              {site.region}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3">
            {footer.columns.map((col) => (
              <div key={col.title}>
                <h3 className="font-mono text-2xs uppercase tracking-[0.18em] text-ink-400">
                  {col.title}
                </h3>
                <ul className="mt-4 space-y-2.5">
                  {col.links.map((l) => (
                    <li key={l.label}>
                      <a
                        href={l.href}
                        className="link-underline inline-flex min-h-[1.75rem] items-center text-sm text-ink-600 transition-colors duration-base ease-out hover:text-ink-900"
                      >
                        {l.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-14 flex flex-col gap-4 border-t border-bone-200 pt-7 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-ink-400">
            © {new Date().getFullYear()} {site.name}. All rights reserved.
          </p>
          <p className="max-w-xl text-xs leading-relaxed text-ink-400">{footer.legal}</p>
        </div>
      </div>
    </footer>
  )
}
