"""The first assistant has no tools, and nothing anywhere has a shell.

`doc/20` A0, `doc/12` P20, I8.

**Why this is worth asserting when there is no tool registry to assert against.**
`domain/untrusted.py` already refuses an externally visible action on a tainted
turn unless a human confirms it with the payload shown — and *every* retrieved
passage taints the turn, by construction. So a tools-capable assistant would
spend its life asking for confirmations, and the temptation when that becomes
annoying is to widen what counts as safe rather than to keep the rule.

This file is written before the temptation exists. It passes trivially today.
The day a tool set appears, granting the assistant one is a red test rather than
a diff nobody questioned.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.domain.untrusted import (
    EXTERNALLY_VISIBLE,
    Turn,
    UntrustedSource,
    requires_confirmation,
    wrap_untrusted,
)

APP = Path(__file__).resolve().parents[1] / "app"

# Names a shell would go by. Matched as whole words against source, so
# `subprocess` in a comment is caught too — a docstring proposing one is worth
# seeing in review.
SHELL_NAMES = ("subprocess", "os.system", "pty.spawn", "shlex.split", "popen")


def test_no_shell_reaches_the_application() -> None:
    """I8. Not assistant-specific, and deliberately global: the assistant is the
    place an injected instruction would aim a shell, so the guarantee has to hold
    everywhere rather than at one boundary."""
    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for name in SHELL_NAMES:
            if re.search(rf"\b{re.escape(name)}\b", source):
                offenders.append(f"{path.relative_to(APP.parent)}: {name}")

    assert offenders == [], f"a shell reached the app: {offenders}"


def test_every_externally_visible_tool_needs_confirmation_on_a_tainted_turn() -> None:
    """The rule the assistant will inherit the day it gains a tool.

    Asserted over the whole set rather than one example, so adding a member to
    `EXTERNALLY_VISIBLE` without the rule covering it is impossible.
    """
    tainted = Turn()
    # A retrieved passage is customer content, and reading one is what taints.
    tainted.read(wrap_untrusted(UntrustedSource.DOCUMENT, "anything at all", ref="chunk:1"))

    assert tainted.tainted
    for tool in EXTERNALLY_VISIBLE:
        assert requires_confirmation(tool, tainted), f"{tool} would proceed unconfirmed"


def test_a_clean_turn_still_needs_no_confirmation() -> None:
    """The other half, so the test above cannot pass by making everything
    require confirmation — which would be a different bug wearing this one's
    clothes."""
    for tool in EXTERNALLY_VISIBLE:
        assert not requires_confirmation(tool, Turn())


def test_reading_a_passage_is_what_taints_and_nothing_untaints() -> None:
    """`Turn.read` is one-directional. Summarising, extracting from or
    translating attacker-controlled text all preserve the instruction inside it,
    so there is no operation that makes it safe — and therefore none that should
    reset this."""
    # Each state is copied into its own local *before* being asserted on.
    # Asserting `turn.tainted` directly narrows the attribute to the dataclass
    # default, and mypy does not widen it again across `read()` — so every later
    # assertion is reported unreachable and the test silently stops meaning
    # anything.
    turn = Turn()
    before = turn.tainted

    turn.read(wrap_untrusted(UntrustedSource.DOCUMENT, "a passage", ref="chunk:1"))
    after_one, blocks_one = turn.tainted, len(turn.blocks)

    turn.read(wrap_untrusted(UntrustedSource.DOCUMENT, "another", ref="chunk:2"))
    after_two, blocks_two = turn.tainted, len(turn.blocks)

    assert before is False
    assert after_one is True
    assert after_two is True, "nothing clears taint"
    assert (blocks_one, blocks_two) == (1, 2), "every passage read is kept for the transcript"
