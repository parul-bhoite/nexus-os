/**
 * Whether the API will get something URL-shaped out of what was typed.
 *
 * Extracted from `components/auth/RegisterCompanyForm.tsx` so the combined
 * onboarding flow's company stage (`components/onboarding/stages/CompanyStage.tsx`)
 * and the old standalone form can share one definition rather than agreeing by
 * copy-paste. See the original's comment for the reasoning this keeps: the API
 * is authoritative and supplies the implied `https://` itself, so this exists
 * only to answer the ordinary typo with a sentence rather than a raw 422. A
 * false accept costs nothing — the server still refuses it; a false reject
 * would block an address the server would have taken, so anything with a dot
 * and no whitespace passes, IDN and unusual TLDs included.
 */
export function looksLikeWebsite(value: string): boolean {
  const host = value
    .trim()
    .replace(/^[a-z][a-z0-9+.-]*:\/\//i, '')
    .split(/[/?#]/)[0]
  return host.includes('.') && !host.startsWith('.') && !host.endsWith('.') && !/\s/.test(host)
}
