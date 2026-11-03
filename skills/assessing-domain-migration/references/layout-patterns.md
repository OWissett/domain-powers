# Layout Patterns

The report's layout section classifies the codebase by the share of units per layer hint. Use it, then confirm by reading the directory tree: the classification is a starting point.

## Technical layering

**Signal:** at least half the units carry technical hints (`models`, `services`, `views`, `utils`...), and the groups are themselves layers (`shop.models`, `shop.services`).

**What it means:** code is organised by what it is, not by what it is for. One business concept is spread across every layer, so scattered terms are high and group-level cycles are common (services call models, models call utils, utils call services).

**Mapping to contexts:**
- Cut across the layers, not along them: the candidate clusters group `models/order`, `services/checkout` and `views/order` together.
- Model-like units become the context's domain; service-like units split between domain behaviour (move into the model) and application orchestration; edge units become adapters.
- Shared units (`utils`, `common`) are usually the last to move: sort their contents by who uses them, and push each piece into the context that owns the concept. What remains is generic.

## Framework apps and feature packages

**Signal:** each group contains model-like, service-like and edge units together (`billing/models`, `billing/services`, `billing/views`).

**What it means:** the codebase is already cut by feature. The seams exist, but they are usually framework apps rather than contexts: they share a database model layer, import each other's internals, and keep business rules in framework hooks.

**Mapping to contexts:**
- Start from the existing packages as candidates; the question is whether each is one context, several, or part of one.
- Check the cross-package edges in the distance table: edges into internals are the work list.
- Two packages that talk constantly may be one context; one package with two vocabularies may be two.

## Mixed layouts

**Signal:** neither pattern holds: some areas layered, some by feature, some flat.

**What it means:** growth in different eras. Do not force one reading on the whole tree.

**Mapping to contexts:**
- Take each region on its own terms, using the matching pattern above.
- Rely on the candidate clusters (dependencies plus shared terms) rather than directory names.
- Expect the glossary to do more work here: names in the tree say less.

## Reading hints with care

- A hint comes from a directory or file name; a `models/` folder full of services is still hinted `models`. Confirm by opening it.
- Units without a hint are not wrong; they simply carry no signal.
- Test units are excluded unless the extractor was run with its test-including option.
