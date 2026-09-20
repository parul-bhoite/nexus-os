"""The assistant: questions answered from the workspace's own documents.

`doc/20`, ADR 0052. **Nothing here reaches a model yet** — A1 is the contracts
and nothing else, so that the import allowlist in
`tests/test_assistant_boundary.py` has something to bind to and the shapes can be
reviewed before any behaviour depends on them.

What this package may import is an allowlist, not a denylist, and three
exclusions carry their reasons in that test: the vendor (ADR 0011), anything that
fetches, and the calculators. A figure is computed by the capability that owns it
and handed here as grounding; it is never recomputed inside an answer.
"""

from app.assistant.contracts import (
    AssistantAnswer,
    AssistantRefusal,
    Citation,
    Question,
)

__all__ = ["AssistantAnswer", "AssistantRefusal", "Citation", "Question"]
