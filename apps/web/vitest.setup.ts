import '@testing-library/jest-dom/vitest'

/**
 * jsdom implements no layout, so it has no `scrollIntoView` — the property is
 * simply absent rather than a no-op. Any component that keeps a transcript
 * pinned to its newest message therefore throws on mount, and the failure names
 * the scroll call rather than whatever the test was actually asserting.
 *
 * Stubbed here rather than per-test: it is a gap in the environment, not a
 * behaviour any test wants to control.
 */
Element.prototype.scrollIntoView = () => {}
