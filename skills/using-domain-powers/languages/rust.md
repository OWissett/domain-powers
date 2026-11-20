# Pack card: Rust

**Detected by:** `Cargo.toml` or `*.rs` files. Edition 2021 or later.

## Config

```toml
# Cargo.toml at the workspace root ([package.metadata.domain-powers] in a single crate)
[workspace.metadata.domain-powers]
contexts = ["ordering", "billing"]   # context crates (hyphens or underscores), or modules in one crate
shared = ["shared_kernel"]           # usable from anywhere, including domain
public_module = "api"                # the only module other contexts may use
domain_forbidden = []                # extra crates or paths, merged with the defaults
```

Layout: a workspace with one crate per context, `crates/<context>/src/{lib.rs, api.rs, domain/, application/, infrastructure/}`, where `lib.rs` declares `pub mod api;` and keeps the layers private. A core context may split its domain into `crates/<context>-domain`. A single crate with one module per context also works. Without the table the guard still checks type escapes and treats any file under a `domain` directory or module as domain.

## Guard codes

| Code | Catches |
|---|---|
| `UNSAFE` | `unsafe` blocks, functions, impls and traits |
| `PANIC` | `.unwrap()`, `.expect(..)`, `panic!`, `todo!`, `unimplemented!`, `unreachable!` |
| `CAST` | `as` to a numeric type, `transmute` |
| `ANY` | `std::any::Any`, `dyn Any`, `downcast` |
| `IGNORE` | `#[allow(..)]`, `#![allow(..)]`, `#[expect(..)]` |
| `DOMAIN-DEP` | domain using a framework or I/O crate (`sqlx`, `diesel`, `sea_orm`, `reqwest`, `hyper`, `axum`, `actix_web`, `tokio`, `serde`, `serde_json`, `aws_sdk_*`…), `std::fs`, `std::net`, `std::process`, `std::env`, or a non-domain module |
| `LAYER` | application using its own context's infrastructure |
| `CROSS-CTX` | a context using another context's internals instead of its `api` |

Test code (`tests/`, `benches/`, `examples/`, and `#[cfg(test)]` items) reports only `IGNORE`. Justification: `// domain-powers: allow <reason>` on the same line, never in a domain layer. Paths are read from `use` items and qualified paths (`sqlx::query(..)`); macro-generated code is left to clippy and the compiler.

## Variants to read

| Skill | Variant |
|---|---|
| type-driven-design | `languages/rust.md`: newtypes, private fields with parsing constructors, enums and typestate, `Result` with error enums |
| modeling-aggregates | `languages/rust.md`: root with private fields, event enums, repository traits, policies |
| testing-invariants | `languages/rust.md`: proptest strategies, command-sequence properties, generic contract suites |
| designing-boundaries | `languages/rust.md`: workspace tree, visibility, cargo-deny bans, trait ports |
| quality-gates | `languages/rust.md`: rustfmt, clippy, cargo check, cargo-deny, cargo test; templates in `languages/rust/` |
| assessing-domain-migration | extractor `scripts/assess/extractors/rust.py .` |

## Reviewer checklist (Rust)

Run, in addition to the agnostic checks:
- `cargo clippy --workspace --all-targets -- -D warnings` and `cargo deny check bans` (if `deny.toml` exists).

Look for:
- `pub` fields on aggregates or value objects; `#[derive(Default)]` or `Deserialize` on domain types.
- `_ =>` arms in matches over domain enums (hides new variants).
- `Box<dyn Error>` or `anyhow` in domain signatures; `String` errors instead of error enums.
- `SystemTime::now()`, `Instant::now()`, random IDs, `std::env`, file or network I/O inside `domain`.
- `rehydrate` (or similar reconstitution constructors) called outside repositories.
- Layer modules made `pub` in a context crate's `lib.rs`, or `pub use` re-exports of domain types from `api`.
- Changes to `[workspace.lints]`, a crate's own `[lints]`, `clippy.toml`, `deny.toml` wrappers, `#[ignore]` on invariant tests, lowered `PROPTEST_CASES`, or deleted `proptest-regressions/` files.
