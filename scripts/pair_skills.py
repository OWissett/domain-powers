#!/usr/bin/env python3
"""domain-powers pairing hook.

PostToolUse on the Skill tool. When a superpowers skill is loaded, inject a short
instruction naming the domain-powers skills that pair with it, so the pairing does
not depend on the model remembering the routing table. Stdlib only.
"""

from __future__ import annotations

import json
import sys

DOCS = "domain-powers:defining-documentation-language"
IMPLEMENTER_NOTE = (
    "When you dispatch implementer subagents for Python domain/application tasks, add this "
    "line to each task prompt: 'Before writing code, load domain-powers:type-driven-design, "
    "domain-powers:modeling-aggregates and domain-powers:testing-invariants, and read "
    "docs/language.md and docs/domain/glossary.md if they exist.' After each task's review, "
    "also dispatch the domain-powers:domain-reviewer agent with the same SHAs."
)

PAIRINGS: dict[str, str] = {
    "brainstorming": (
        "Also load domain-powers:modeling-the-domain (glossary, events, bounded contexts) and "
        f"{DOCS} (read or create docs/language.md before writing the design doc)."
    ),
    "writing-plans": (
        "Also load domain-powers:designing-boundaries (context/layer/invariants per task, "
        f"contracts before code) and {DOCS} (plan, task, step, batch, round per docs/language.md)."
    ),
    "test-driven-development": (
        "For Python domain or application code, also load domain-powers:type-driven-design, "
        "domain-powers:modeling-aggregates and domain-powers:testing-invariants."
    ),
    "subagent-driven-development": IMPLEMENTER_NOTE,
    "executing-plans": IMPLEMENTER_NOTE,
    "dispatching-parallel-agents": IMPLEMENTER_NOTE,
    "requesting-code-review": (
        "Also dispatch the domain-powers:domain-reviewer agent with the same BASE_SHA, HEAD_SHA "
        "and plan task, plus the paths to docs/domain/glossary.md and docs/language.md."
    ),
    "verification-before-completion": (
        "Also load domain-powers:quality-gates: the evidence is a fresh run of every gate in "
        "scripts/check.sh."
    ),
    "finishing-a-development-branch": (
        "Before finishing, load domain-powers:quality-gates and run every gate fresh."
    ),
    "systematic-debugging": (
        "Once the root cause is found: if it was an invalid state, load "
        "domain-powers:type-driven-design to make it unrepresentable; add the failing case as a "
        "Hypothesis @example (domain-powers:testing-invariants)."
    ),
    "writing-skills": f"Also load {DOCS}: skills use the terms in docs/language.md.",
}


def skill_name(tool_input: object) -> str | None:
    if not isinstance(tool_input, dict):
        return None
    for key in ("skill", "command", "name"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value.strip().lstrip("/")
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") != "Skill":
        return 0
    name = skill_name(payload.get("tool_input"))
    if name is None:
        return 0
    plugin, _, bare = name.rpartition(":")
    if plugin not in ("", "superpowers"):
        return 0
    note = PAIRINGS.get(bare)
    if note is None:
        return 0
    context = f"domain-powers pairs with superpowers:{bare}. {note}"
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
