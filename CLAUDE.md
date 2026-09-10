# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`sillystrings` is a pure-Python reimplementation of the Unix `strings` utility: it extracts printable character sequences from binary files. Python 3.11+, src layout, managed with `uv`, zero runtime dependencies, published to PyPI as `sillystrings`.

## Commands

- **Install deps:** `just install` (`uv sync` + `uv run pre-commit install`)
- **Run the CLI locally:** `just run --help` (`uv run sillystrings --help`)
- **Run tests:** `just test` (`uv run pytest`)
- **Run single test:** `uv run pytest --no-cov tests/test_scanner.py::TestScanner::test_scan -v` (`--no-cov` is required — the coverage gate in `addopts` fails any partial run)
- **Test with coverage (100% gate):** `just test-cov` (`uv run pytest --cov --cov-fail-under=100`)
- **Format:** `just format` (`uv run ruff format src/ tests/`)
- **Format check:** `just format-check` (`uv run ruff format --check src/ tests/`)
- **Lint (auto-fix):** `just lint` (`uv run ruff check --fix src/ tests/`)
- **Lint check:** `just lint-check` (`uv run ruff check src/ tests/`)
- **Type check:** `just typecheck` (`uv run ty check src/`)
- **Everything:** `just check` (format-check + lint-check + typecheck + test-cov)
- **Clean caches:** `just clean`
- **Upgrade lockfile:** `just lock-upgrade`
- **Bump version:** `just bump-version <major|minor|patch|dev|beta|alpha|rc>` (`uv version --bump <part>`)

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
- **The 100% coverage gate lives in `[tool.pytest.ini_options] addopts`, not in the CI step**, so `ci.yml` stays byte-identical across the project family. Side effect: it applies to every local `pytest` run, so a partial run (`pytest tests/test_cli.py`) will fail on coverage — that is expected, not a broken test.
- **Scanning is the hot path.** `iter_chars` calls a predicate once per byte; see #31 for the pending lookup-table optimization. Be wary of adding per-byte work.

## Workflow

- Every feature, fix, or other change gets its own branch and pull request — no direct commits to main.
- Commits must be atomic and follow Conventional Commits (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `deps`): one logical change per commit.
- PRs that resolve an issue reference it with `Closes #N` so it closes automatically on merge.
- **PRs are merged with a merge commit** — never squashed or rebased. Both break stacked PRs, and this project family works in stacks.
- **Keep `CHANGELOG.md` release-ready.** Any user-facing change adds a bullet under `## [Unreleased]` in the same PR (internal-only refactors, CI, test, and docs changes are exempt). Entries follow the existing Keep a Changelog style — grouped under `### Added`/`### Changed`/`### Fixed`/`### Removed`, one line each, ending with the PR ref `(#N)`.
- **Releases are automated and notes come from the changelog — never hand-written commit dumps.** Cutting a release starts locally with `just bump-version <part>`; there is deliberately no bump-version workflow, because PRs opened with `GITHUB_TOKEN` never trigger workflows and so could never satisfy required checks. The CD workflow publishes to PyPI when the bump lands on `main`, then publishes a GitHub release whose body is that version's `CHANGELOG.md` section (extracted between its `## [x.y.z]` heading and the next; it fails the release if the section is missing). See CONTRIBUTING.md → Releasing.

## Code Style

- Google-style docstrings (enforced by ruff).
- Line length: 88 chars.
- Ruff `select = ["ALL"]` with a pragmatic, curated set of ignores (see `pyproject.toml`).
- Tests are exempt from docstring and type-annotation rules, and from `FBT001` since parametrized signatures take booleans positionally.
- Prefer comments that explain *why* code does something, not *what* it does.

## Testing Notes

- 100% branch coverage is a hard gate — every new branch needs a test.
- Scanner and encoding behavior live in large parametrized tables in `tests/test_scanner.py` and `tests/test_encodings.py`. Add a row rather than a new test function where the case fits, and put the case comment *above* the tuple so the row stays on one line at 88 chars.
- Build inputs with `make_data` from `tests/conftest.py`: string segments are encoded for the target encoding, `int` segments become that many NUL characters, and `bytes` segments are appended raw — which is how to construct odd-length or malformed buffers.
- CLI tests come in two layers: subprocess smoke tests through the `run` helper (which shell out via `uv run sillystrings` and are invisible to coverage) and in-process tests that import from `cli.py`. A new branch in `cli.py` needs an in-process test to satisfy the gate.
