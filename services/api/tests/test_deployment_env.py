"""The deployed environment's required variables, in one place, generated.

`doc/12` P9: *secrets from the environment, not a file; document the required
set in one place generated from `Settings`.* A hand-written list of environment
variables is a list that drifts — silently, and the way you find out is a
deployment that boots and then fails on the first request that needs the
setting nobody wrote down.

So the document is generated from `Settings` and this test regenerates it and
compares. Adding a required secret without updating the deploy documentation
fails here, at the point the secret is added.
"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings

DOC = Path(__file__).resolve().parents[3] / "doc" / "DEPLOYMENT-ENV.md"


def render() -> str:
    """The document, from `Settings`. The single source is the model."""
    # Read through `__private_attributes__` because pydantic wraps a private
    # attribute in `ModelPrivateAttr` on the class — mypy sees the annotated
    # tuple, the runtime sees the wrapper, and only one of them is right.
    # Reading it off an *instance* would work and would also build a `Settings`,
    # which needs an environment this test should not require.
    private = Settings.__private_attributes__["_DEPLOYED_REQUIRES"]
    names: tuple[str, ...] = private.get_default()
    required = [f"NEXUS_{name.upper()}" for name in names]

    lines = [
        "# Required environment",
        "",
        "**Generated from `Settings`. Do not edit by hand** —",
        "`tests/test_deployment_env.py` regenerates this and fails if it disagrees.",
        "",
        "A hand-written list of environment variables drifts, and the way you find out",
        "is a deployment that boots and then fails on the first request needing the",
        "setting nobody wrote down.",
        "",
        "## Refused at startup when missing",
        "",
        "In any environment other than `local` and `ci`, the process refuses to start",
        "and names **every** missing variable at once — a deployment fixing them one",
        "restart at a time is a deployment being told the truth slowly.",
        "",
    ]
    lines += [f"- `{name}`" for name in required]
    lines += [
        "",
        "`NEXUS_ENV` has no default and is required everywhere, including locally",
        "(ADR 0015): a missing value used to mean `local`, which is how a production",
        "process ends up with insecure cookies and the docs page open.",
        "",
        "## Optional, and absent is a supported state",
        "",
        "- `NEXUS_ANTHROPIC_API_KEY` — without it the language model reports",
        "  `unconfigured` and refuses rather than inventing (ADR 0011).",
        "- `NEXUS_JOBS_DATABASE_URL` — the `nexus_jobs` role for maintenance lookups",
        "  that RLS hides from the app role (ADR 0018).",
        "- `NEXUS_RUN_SCHEDULER` — **true on exactly one container**, the worker.",
        "  Every API process running every job means one copy of each sweep per",
        "  replica, and the jobs are idempotent rather than exclusive, so the symptom",
        "  is load rather than an error anybody sees.",
        "- `NEXUS_PROXY_TIMEOUT_MS` — the BFF's budget, 30s by default (finding #23).",
        "",
    ]
    return "\n".join(lines)


def test_the_deployment_document_matches_settings() -> None:
    """Regenerate and compare.

    If this fails, run it with `NEXUS_WRITE_ENV_DOC=1` to rewrite the file, then
    read the diff — it is the list of secrets a deployment now needs.
    """
    import os

    expected = render()
    if os.environ.get("NEXUS_WRITE_ENV_DOC"):
        # `encoding="utf-8"` on both sides, and the *write* is the dangerous one.
        # `write_text` without it encodes in the locale codepage — cp1252 on
        # Windows — so regenerating this document on a developer's machine would
        # commit a mojibake version of it. The read has the mirror of the same
        # fault: it decodes UTF-8 as cp1252 and the comparison fails on an
        # em-dash that is identical in both files.
        DOC.write_text(expected, encoding="utf-8")

    assert DOC.exists(), f"{DOC} is missing; regenerate with NEXUS_WRITE_ENV_DOC=1"
    assert DOC.read_text(encoding="utf-8") == expected, (
        "doc/DEPLOYMENT-ENV.md disagrees with Settings. "
        "Regenerate with NEXUS_WRITE_ENV_DOC=1 and read the diff."
    )
