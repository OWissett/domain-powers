# Codex

## Load paired skills

Use the routing table in `using-domain-powers` after loading the matching
superpowers skill. Codex has no Claude `Skill` tool: read each paired `SKILL.md`
with filesystem tools, relative to the installed plugin root. For brainstorming,
read `skills/modeling-the-domain/SKILL.md` and
`skills/defining-documentation-language/SKILL.md`. Native invocation uses names
such as `$modeling-the-domain`; `domain-powers:` names identify this plugin's
skills but do not require a namespaced tool.

For a skills-only installation, resolve the discovered `SKILL.md` symlink to its
real path; the plugin root is three directories above that file. Keep the complete
repository layout so references and scripts remain available.

## Hooks and gates

Manual Codex desktop plugin installation can load the packaged SessionStart and
PostToolUse hooks after the user reviews and trusts them. SessionStart supplies
the routing table and this reference. PostToolUse checks native `apply_patch`
edits. It does not undo an edit when it reports a finding.

Codex has no Claude `Skill` event, so apply the routing table yourself when loading
superpowers skills. Shell writes are not covered by the patch hook. Run the shared
guard after shell edits and before completion:

```bash
python3 <plugin-root>/scripts/domain_guard.py --scan src docs README.md
```

A skills-only installation has no lifecycle hooks. Read `using-domain-powers`
explicitly at the start of work and run the guard manually. Do not claim automatic
edit enforcement without a trusted plugin hook. The quality-gates skill supplies
the rest of the verification commands for a project.

## Domain review

When a review is required and a generic subagent tool is available, read
`<plugin-root>/agents/domain-reviewer.md` and use its review instructions as the
subagent prompt. Supply the diff or base/head revisions, plan task, and paths to
the project's glossary and documentation language. Load its paired skills through
filesystem tools. A Claude named-agent registry is not required.

Without subagent support, perform that checklist yourself and report that the
review was not independent. Do not invent unavailable tools or claim that a
named agent ran.
