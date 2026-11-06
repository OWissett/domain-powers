# Quality Gates: Rust

## Command map

| # | Gate | Command | Configured to catch |
|---|---|---|---|
| 1 | Format | `cargo fmt --all --check` | |
| 2 | Lint | `cargo clippy --workspace --all-targets -- -D warnings` | `unwrap_used`, `expect_used`, `panic`, `todo`, `unimplemented`, `unreachable`, `as_conversions`, `indexing_slicing`, `wildcard_enum_match_arm`, `allow_attributes_without_reason`, the `pedantic` group; `unsafe_code` forbidden |
| 3 | Types | `cargo check --workspace --all-targets` | The compiler: exhaustive matches, private modules, ownership |
| 4 | Boundaries | `cargo deny check bans` | Frameworks only in listed crates; a context's domain crate used only by its own context |
| 5 | Escape audit | `python3 scripts/domain-powers/domain_guard.py --scan crates` | `UNSAFE`, `PANIC`, `CAST`, `ANY`, `IGNORE`, boundary codes inside crates (layer rules the compiler can't see) |
| 6 | Tests | `PROPTEST_CASES=500 cargo test --workspace` | |
| 7 | Language | `python3 scripts/domain-powers/domain_guard.py --scan docs README.md` | `TERM` |
| 8 | Migration | `extractors/rust.py .`, `core.py analyse`, `core.py compare` | |

Gates 2 and 5 overlap on purpose: clippy sees through macros and types; the guard sees layers and contexts, and runs on every edit.

## Setup

1. Merge `languages/rust/Cargo-template.toml` (in this skill's directory) into the workspace `Cargo.toml`: `[workspace.lints]` and `[workspace.metadata.domain-powers]`. Add `[lints] workspace = true` and `publish = false` to every member crate.
2. Copy `languages/rust/clippy-template.toml` to `clippy.toml` (test allowances) and `languages/rust/deny-template.toml` to `deny.toml`, then list your framework crates and their allowed wrappers.
3. Install tools: `rustup component add rustfmt clippy`, `cargo install cargo-deny --locked`. Add `proptest` to each context crate's `[dev-dependencies]`.
4. Copy `references/check.sh` to `scripts/check.sh` and vendor the tools into `scripts/domain-powers/`. Set `SRC=crates` (the default for Rust) if your crates live elsewhere.
5. Commit `Cargo.lock` and `proptest-regressions/`.

## Brownfield lists

- **Lints:** a legacy crate may override `[lints]` in its own `Cargo.toml` instead of inheriting the workspace table; list only that crate, never a context crate or a domain crate. Inside a crate, a legacy module may carry `#![allow(clippy::unwrap_used, reason = "legacy, issue #123")]` at its top. Both lists may only shrink.
- **Boundaries:** `deny.toml` `wrappers` entries for legacy crates, each with a comment linking to an issue. That list may only shrink.
- **Unsafe:** a crate that truly needs `unsafe` sets `unsafe_code = "deny"` in its own `[lints.rust]` and wraps each block in `#[allow(unsafe_code, reason = "...")] // domain-powers: allow <reason>`. Never a domain crate or module.

## Never do this to go green (Rust spellings)

- `#[allow(..)]`, `unsafe`, `.unwrap()`, `as` casts without `// domain-powers: allow <reason>`
- Removing a lint from `[workspace.lints]`, lowering it to `allow`, or dropping `-D warnings`
- Adding a crate to a `wrappers` list, or removing a `deny` entry
- `#[ignore]` on an invariant test, or lowering `PROPTEST_CASES` / `with_cases` to make it pass
- Deleting a `proptest-regressions/` file
