"""What `app/assistant/` may reach, written before it exists.

`doc/20` A0. This is an **allowlist**, not a denylist, and the direction is the
whole point: a denylist has to predict what a future author will import, and the
assistant is the one surface in this product where an unplanned dependency is
most costly — it is the module that will put customer text in front of a model.

Three kinds of thing it must not reach, each for its own reason:

- **The vendor.** ADR 0011 keeps the provider name inside `app/ai/`. The
  assistant depends on `app.ai.contracts` and the runtime, never on the module
  that knows who implements them.
- **Anything that fetches.** `app.research.*` and the connectors go out to the
  network. An assistant that could crawl is an assistant an injected instruction
  could aim, and `EXTERNALLY_VISIBLE` in `domain/untrusted.py` exists because
  that class of action is the one worth confirming. `connectors.rate_limit` is
  the single exception — it counts, it does not reach anything.
- **Calculators and routes.** A figure must be computed by the capability that
  owns it and handed to the assistant as grounding, never recomputed inside an
  answer. Importing a route module would also invert the layering.

**It passes trivially today**, because `app/assistant/` does not exist. That is
deliberate: written now, the day the package appears the rule is already there,
and adding a forbidden import is a red test rather than a code review somebody
might not get to.
"""

from __future__ import annotations

from tests.test_no_unauthenticated_crawl import _import_graph

PACKAGE = "app.assistant"

# Prefixes `app.assistant.*` may import. Anything under `app.` not matching one
# of these is a failure; standard library and third-party imports are not in the
# graph at all, which only records `app.`-internal edges.
PERMITTED: frozenset[str] = frozenset(
    {
        "app.assistant",
        "app.retrieval",
        "app.embeddings.registry",
        "app.embeddings.contracts",
        "app.grounding.pipeline",
        "app.grounding.ledger",
        "app.domain.untrusted",
        "app.domain.session",
        "app.domain.scopes",
        "app.domain.access",
        "app.ai.runtime",
        "app.ai.contracts",
        "app.connectors.rate_limit",
        "app.config",
        "app.logging",
        "app.db",
    }
)


def _is_permitted(module: str) -> bool:
    return any(module == p or module.startswith(f"{p}.") for p in PERMITTED)


def _assistant_modules(graph: dict[str, set[str]]) -> list[str]:
    return [m for m in graph if m == PACKAGE or m.startswith(f"{PACKAGE}.")]


def test_the_assistant_imports_only_what_it_is_allowed_to() -> None:
    graph = _import_graph()
    modules = _assistant_modules(graph)

    offences: list[str] = []
    for module in modules:
        for imported in sorted(graph[module]):
            if not _is_permitted(imported):
                offences.append(f"{module} -> {imported}")

    assert offences == [], (
        "the assistant reached outside its allowlist: "
        + "; ".join(offences)
        + ". Widening `PERMITTED` is a decision, not a fix — say why in the commit."
    )


def test_the_assistant_never_names_the_vendor() -> None:
    """ADR 0011, applied to the surface most likely to break it.

    `test_ai_boundary.py` already asserts this product-wide and reads prose as
    well as imports. Repeated here narrowly because the assistant is where a
    provider-specific import is most tempting — a retry, a token count, a
    model-specific parameter — and a failure naming *this* package is a clearer
    signal than one naming the whole app.
    """
    graph = _import_graph()

    for module in _assistant_modules(graph):
        assert "app.ai.anthropic_provider" not in graph[module], (
            f"{module} imports the provider directly; depend on app.ai.contracts"
        )


def test_the_rule_is_ready_before_the_package_is() -> None:
    """The guard's own precondition.

    If `app/assistant/` is ever renamed, the two tests above would pass by
    finding nothing — the most comfortable kind of false green. This states the
    current expectation out loud so that the day the package lands, the
    assertions are known to be looking at it.
    """
    graph = _import_graph()
    found = _assistant_modules(graph)

    if not found:
        # A0's own acceptance: the allowlist exists before the code does.
        assert PACKAGE not in graph
    else:
        assert all(m.startswith(PACKAGE) for m in found)
