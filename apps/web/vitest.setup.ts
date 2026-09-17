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

/**
 * `ResizeObserver` likewise. jsdom has no layout engine, so it ships no
 * implementation and the global is undefined rather than inert — a component
 * that observes its own width to decide whether it overflows throws on mount,
 * and the error names the observer rather than the assertion that was running.
 *
 * A stub that never fires is the honest shape for this environment. Nothing in
 * jsdom will ever resize, so an observer that reported a change would be
 * inventing one; what the stub restores is only that constructing it does not
 * explode. Components are expected to render correctly before their first
 * observation, which is a property worth having anyway — it is what makes the
 * server-rendered markup right.
 */
class NoopResizeObserver implements ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver ??= NoopResizeObserver
