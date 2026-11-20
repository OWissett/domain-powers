# Extractor Contract

An extractor reads source code and writes a neutral model as JSON. `core.py` never parses source, so adding a language means adding one extractor and nothing else. An extractor may be written in any language, as long as it honours this contract.

## Command line

```
<extractor> <source_root> --out model.json [--package NAME] [--include-tests] [--exclude GLOB ...]
```

- Exit 0 on success, even with skipped files. Exit 2 on usage errors or an unreadable root.
- Tests are excluded by default: units with `layer_hint: tests` are dropped unless `--include-tests` is given.
- `--exclude` takes globs, repeatable, for generated or vendored code.
- The core currently accepts only the six capability names listed in the schema below; an unknown one is a model error (exit 2).
- Output is deterministic: units sorted by `id`, edges by `(from, to)`; the same code gives the same bytes.

## Model schema

Schema id: `domain-powers.assess.model/1`.

```json
{
  "schema": "domain-powers.assess.model/1",
  "language": "python",
  "root": "src",
  "capabilities": ["edges", "types", "data_only", "escapes", "framework_refs", "layer_hints"],
  "units": [
    {
      "id": "shop.models.order",
      "path": "src/shop/models/order.py",
      "group": "shop.models",
      "loc": 120,
      "layer_hint": "models",
      "types": [{"name": "Order", "data_only": true}],
      "escapes": {"ANY": 2, "IGNORE": 1},
      "framework_refs": ["sqlalchemy"]
    }
  ],
  "edges": [{"from": "shop.services.billing", "to": "shop.models.order", "count": 3}],
  "skipped": [{"path": "src/shop/broken.py", "reason": "syntax error"}]
}
```

| Field | Meaning | Capability |
|---|---|---|
| `units[].id` | Stable logical name (module path, crate and module, file path) | always |
| `units[].group` | Package-level grouping used for package metrics | always |
| `units[].loc` | Non-blank, non-comment lines | always |
| `units[].layer_hint` | One of the hint vocabulary below, or `null` | `layer_hints` |
| `units[].types` | Declared type names | `types` |
| `types[].data_only` | No behaviour beyond construction, accessors and derived or built-in methods | `data_only` |
| `units[].escapes` | Counts by kind (`ANY`, `CAST`, `IGNORE`, `UNTYPED`, or language-specific kinds) | `escapes` |
| `units[].framework_refs` | Framework or I/O libraries the unit uses | `framework_refs` |
| `edges` | Internal dependencies only (both ends are units) | `edges` |
| `skipped` | Files the extractor could not read, with reason | always |

## Layer-hint vocabulary

`models`, `entities`, `schemas`, `services`, `managers`, `handlers`, `views`, `controllers`, `routes`, `api`, `repositories`, `dao`, `serializers`, `forms`, `tasks`, `utils`, `helpers`, `common`, `core`, `domain`, `application`, `infrastructure`, `adapters`, `tests`.

Map directory or file names onto this list (`repos` becomes `repositories`) and emit `null` otherwise.

Hints fall into four groups, which the layout and domain metrics use:

| Group | Hints |
|---|---|
| model-like | `models`, `entities`, `schemas`, `domain` |
| service-like | `services`, `managers`, `handlers`, `application` |
| edge | `views`, `controllers`, `routes`, `api`, `serializers`, `forms`, `adapters`, `infrastructure`, `repositories`, `dao`, `tasks` |
| shared | `utils`, `helpers`, `common`, `core` |

## Capabilities

List in `capabilities` only what the extractor really produces. **A capability that is not declared means not applicable, never zero:** the core leaves out every metric that needs it and says so in the report. An extractor that cannot tell data-only types from others must omit `data_only`, not emit `false`.

## Shipped extractors

| Language | Detected by | Command |
|---|---|---|
| `python` | `*.py` files, or `pyproject.toml` / `setup.py` / `setup.cfg` | `python3 <tools>/extractors/python.py src --out model.json` |
| `rust` | `*.rs` files, or `Cargo.toml` | `python3 <tools>/extractors/rust.py . --out model.json` |

`<tools>` is the directory holding this file: `scripts/assess/` in the plugin, or `scripts/domain-powers/assess/` where a project vendors the tools. Add `--package NAME`, `--include-tests` or `--exclude GLOB` as needed.

Notes per extractor:

- **python:** units are modules; `--package` names the root package when it cannot be inferred.
- **rust:** the source root is a workspace or crate directory. Units are `.rs` files under each crate's `src/`, with ids `crate::module::path` (crate names with `-` become `_`). With one crate, or the crate named by `--package`, groups are the crate's top-level modules; other crates are one group each. `data_only` counts constructors (`new`, `default`, `from_*`, `with_*`) and field accessors as data; trait impls are ignored. Tests are files under `tests/`, `benches/` and `examples/`, plus `#[cfg(test)]` items. `target/` is never read.

## Writing an extractor

Add it under `extractors/`, named by language, and a row to the table above. An extractor written in Python should take its escape and framework detection from the guard's language pack (`languages/<language>.py`), so the model counts exactly what the guard reports.
