# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`sillystrings` is a pure-Python reimplementation of the Unix `strings` utility: it extracts printable character sequences from binary files. Python 3.11+, src layout, managed with `uv`, zero runtime dependencies. Not yet published — the first PyPI release is #27.

## Commands

Recipes live in the `justfile`; `just` (or `just --list`) prints them with their descriptions. Do not restate their expansions here — that is what rots.

- `just install` — sync the venv and install the git hooks
- `just run --help` — drive the CLI locally
- `just test` / `just test-cov` — the suite (identical today: the coverage gate lives in `addopts`, so it applies to every run)
- `just format` / `just format-check`, `just lint` / `just lint-check`, `just typecheck`
- `just check` — everything, in the order CI will run it
- `just clean`, `just lock-upgrade`, `just bump-version <part>`

**Run a single test:** `uv run pytest --no-cov tests/test_scanner.py::TestScanner::test_scan -v`. The `--no-cov` is required — the gate in `addopts` fails any partial run.

Note the ruff recipes are scoped to `src/ tests/` while `ruff check .` covers the repo including `scripts/`; both are clean and both must stay that way, since the pre-commit hooks run over every staged file.

## Architecture

The project uses a `src/sillystrings/` layout with three modules in a strict dependency line — `cli.py` → `scanner.py` → `encodings.py`:

- `encodings.py` — The encoding vocabulary and the per-character printability rules. Defines `Encoding` (the `Literal["s", "S", "l", "b"]` alias), the `ASCII_ENCODINGS` / `UTF16_ENCODINGS` tuples both dispatchers switch on, `unsupported_encoding()` for the shared error, the `is_printable_ascii` / `is_printable_utf16` predicates, and `iter_chars()` — which walks a buffer yielding `(offset, printable)` pairs.
- `scanner.py` — `scan()`, the public API. Dispatches on encoding to `_scan_ascii` or `_scan_utf16`, which accumulate runs of printable characters and yield `(offset, string)` for every run meeting `min_length`. Both accumulators flush a trailing run after the loop.
- `cli.py` — The argparse entry point. Builds the parser, resolves file/stdin sources into `Source` records, formats offsets by radix, and prints results.

Key design decisions:

- **The encoding letters are defined once, in `encodings.py`.** `cli.py` derives its `-e` choices from `get_args(Encoding)` rather than repeating the list, so the flag cannot drift from what `scan()` accepts. Before this was consolidated the four letters appeared in eight places across four files. Do not reintroduce a literal encoding list.
- **An unsupported encoding raises `ValueError`, it does not yield nothing.** Both `scan()` and `iter_chars()` have an explicit `else` on their dispatch. Since both are generators, the error surfaces on first consumption, not at call time — tests must wrap the call in `list()`. `is_printable_ascii` is the deliberate exception: it returns `False` for UTF-16 encodings because those are handled by `iter_chars`, not by it.
- **`include_ws` is keyword-only** across `encodings.py`, matching `scan()`'s pre-existing keyword-only signature. This was chosen over globally ignoring ruff's `FBT001`/`FBT002`.
- **The 100% coverage gate lives in `[tool.pytest.ini_options] addopts`, not in the CI step**, so `ci.yml` stays byte-identical across the project family (design.md A2).
- **Scanning is the hot path.** `iter_chars` calls a predicate once per byte; see #31 for the pending lookup-table optimization. Be wary of adding per-byte work.

## Workflow

- Every feature, fix, or other change gets its own branch and pull request — no direct commits to main.
- Commits must be atomic and follow Conventional Commits (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `deps`): one logical change per commit.
- PRs that resolve an issue reference it with `Closes #N` so it closes automatically on merge.
- **PRs are merged with a merge commit** — never squashed or rebased. Both break stacked PRs, and this project family works in stacks.
- **Keep `CHANGELOG.md` release-ready.** Any user-facing change adds a bullet under `## [Unreleased]` in the same PR (internal-only refactors, CI, test, and docs changes are exempt). Group entries under `### Added`/`### Changed`/`### Fixed`/`### Removed` and end each with the PR ref `(#N)`. The seed entries under `[Unreleased]` predate this rule and carry no refs — follow the rule, not those.
- **Releases are automated and notes come from the changelog — never hand-written commit dumps.** Cutting a release starts locally with `just bump-version <part>`; the CD workflow then publishes to PyPI and creates a GitHub release whose body is that version's `CHANGELOG.md` section. See CONTRIBUTING.md → Releasing for the bump-choice table and the reasoning. **None of this exists yet** — CI is #22 and the release pipeline is #27.

## Code Style

- Google-style docstrings (enforced by ruff).
- Line length: 88 chars.
- Ruff `select = ["ALL"]` with a pragmatic, curated set of ignores (see `pyproject.toml`).
- Tests are exempt from docstring and type-annotation rules, and from `FBT001` since parametrized signatures take booleans positionally.
- Prefer comments that explain *why* code does something, not *what* it does.

## Testing Notes

The testing conventions — parametrized tables, `make_data`, and the two CLI test layers — are documented once, in CONTRIBUTING.md → Testing. Read that rather than a paraphrase here.

The one thing worth repeating: subprocess CLI tests are invisible to coverage, so a new branch in `cli.py` needs an in-process test to satisfy the gate.
