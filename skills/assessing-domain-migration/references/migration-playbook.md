# Migration Playbook

How to move one slice without breaking anything or the gates. The loop is the same for every slice; only the contexts differ.

## Slices

One slice moves one context, or part of one, behind its boundary, and ends with every gate green. Never plan "move everything": a slice that cannot be reviewed in one sitting is too large. Split it by units, keeping each half green.

## Ordering rule

Fewest incoming cross-context edges first: a context nobody depends on can move without touching callers. Exception: if the human partner prioritises the core context by churn, move it first and accept the extra shims. Record the choice in the report's Slices section.

## The loop

1. **Skeleton in warn mode.** Create the context package and its boundary rules. Set the rules to warn, and record every current violation as an exception, each with a comment naming the slice. Exceptions only shrink: growth is a failed gate.
2. **Move units with shims.** Move the context's units into it. Leave the old import path behind as a re-export shim so callers keep working. Record each shim as an exception too.
3. **Add the `api` facade.** The one place other contexts may import from. Point callers at it as you touch them.
4. **Add anti-corruption layers for legacy callers.** Where a legacy caller needs a shape the new model should not adopt, translate at the border instead of bending the model. The layer belongs to the legacy side and is deleted with it.
5. **Shrink to zero.** Repoint remaining callers at the `api` facade, delete the shims, empty the exception lists, and switch the rules from warn to strict.
6. **Refresh the baseline.** Only now, with a new `assessment.json` that shows the work list smaller. A refresh that hides an increase is a weakened gate.

## Target patterns

The `units` patterns in `target.toml` must match each context's current locations and the locations its units will move to, so the distance table is meaningful before, during and after the move. Editing `target.toml` switches off the three target-dependent ratchet metrics until the baseline is refreshed (`compare` prints "targets differ"), so treat a change to it as a baseline refresh: make it only at a slice end, and have it reviewed.

## Warn-then-strict boundaries

Strict rules on day one fail on every legacy import and get switched off. Warn mode with recorded exceptions keeps the rules alive while the code catches up. The exception list is the slice's progress bar: it must be non-increasing in every change, and empty when the slice ends. See `domain-powers:quality-gates` (brownfield section) for the language's exception lists and how to keep them shrinking.

## Re-export shims

A shim is a stub at the old path that re-exports from the new one. It buys one thing: callers need not change in the same change as the move. It costs a boundary exception and a line in the exception list, so it is temporary by construction. Never add a shim that no caller needs, and never add logic to one.

## `api` facades

A context's public surface: a small set of names that other contexts may use. Everything else is internal. Put the facade where the target's `public` patterns point, so the distance table counts calls through it as legitimate. Keep it narrow; widening it to pass a check hides the coupling instead of removing it.

## Anti-corruption layers

When a legacy module still speaks the old model, put a translator between it and the new `api`, owned by the legacy side. Do not leak the old shape into the new context to save the translation. When the last legacy caller goes, delete the layer.

## Review checks per change

- Does the change belong to the current slice?
- Did the exception lists shrink, or at least not grow?
- Did it add a shim nobody needs?
- Does `compare` exit 0, and does the delta table show progress?
