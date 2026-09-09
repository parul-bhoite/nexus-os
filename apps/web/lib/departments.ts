/**
 * The seven department keys, for the BFF routes that interpolate one.
 *
 * Shared rather than repeated. Both dashboard routes take a `[department]`
 * segment and both must refuse anything else before it reaches the API — and
 * two copies of a validation set is how the weaker one ends up on the newer
 * route. The reason is the same one the invitation id carries: an unvalidated
 * segment lets a caller append their own path and reach an endpoint the route
 * was never meant to expose.
 *
 * It mirrors `app.domain.scopes.Department`. A key added there and not here
 * gets a 404 from the proxy, which is a confusing failure for a department that
 * exists — so they move together.
 */
export const DEPARTMENTS: ReadonlySet<string> = new Set([
  'marketing',
  'sales',
  'finance',
  'operations',
  'hr',
  'strategy',
  'executive',
])
