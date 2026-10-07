# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`sillystrings` is a pure-Python reimplementation of the Unix `strings` utility: it extracts printable character sequences from binary files. Python 3.11+, src layout, managed with `uv`, zero runtime dependencies. Published on PyPI.

## Commands

Recipes live in the `justfile`; `just` (or `just --list`) prints them with their descriptions. Do not restate their expansions here — that is what rots.

- `just install` — sync the venv and install the git hooks
- `just run --help` — drive the CLI locally
- `just test` / `just test-cov` — the suite without / with the 100% coverage gate (the gate lives in `addopts`; `just test` opts out with `--no-cov`)
- `just format` / `just format-check`, `just lint` / `just lint-check`, `just typecheck`
- `just check` — everything, in the order CI will run it
- `just clean`, `just lock-upgrade`, `just bump-version <part>`

**Run a single test:** `uv run pytest --no-cov tests/test_scanner.py::TestScanner::test_scan -v`. The `--no-cov` is required — the gate in `addopts` fails any partial run.

Note the ruff recipes are scoped to `src/ tests/` while `ruff check .` covers the repo including `scripts/`; both are clean and both must stay that way, since the pre-commit hooks run over every staged file.

## Architecture

The project uses a `src/sillystrings/` layout. Its modules form two strict dependency lines from the CLI — `cli.py` → `scanner.py` → `encodings.py`, and `cli.py` → `formats/` → `formats/common.py`. The format parsers never import the scanner.

- `encodings.py` — The encoding vocabulary and the per-character printability rules. Defines `Encoding` (the `Literal["s", "S", "l", "b", "L", "B"]` alias), the `ASCII_ENCODINGS` tuple and the `WIDE_ENCODINGS` map (encoding → character width and byte order) that both dispatchers switch on, `unsupported_encoding()` for the shared error, the `is_printable_ascii` / `is_printable_wide` predicates, and `iter_chars()` — which walks a buffer yielding `(offset, printable)` pairs.
- `scanner.py` — `scan()`, the public API. Dispatches on encoding to `_scan_ascii` or `_scan_wide`, which accumulate runs of printable characters and yield `(offset, string)` for every run meeting `min_length`. Both accumulators flush a trailing run after the loop.
- `formats/` — Object file parsers for `-d`. `data_ranges(data)` in `__init__.py` tries each format's `data_sections()` in turn (Mach-O for now; ELF, #3, is one more `_PARSERS` entry) and returns `(offset, size)` file ranges, or `None` meaning "scan the whole file". `macho.py` parses thin Mach-O; `common.py` holds the `Section(name, offset, size)` record.
- `cli.py` — The argparse entry point. Builds the parser, checks every path up front, then opens each source in turn with `open_source()` (a context manager yielding a `Source`), formats offsets by radix, and prints results.

Key design decisions:

- **The encoding letters are defined once, in `encodings.py`.** `cli.py` derives its `-e` choices from `get_args(Encoding)` rather than repeating the list, so the flag cannot drift from what `scan()` accepts. Before this was consolidated the four letters appeared in eight places across four files. Do not reintroduce a literal encoding list.
- **An unsupported encoding raises `ValueError`, it does not yield nothing.** Both `scan()` and `iter_chars()` have an explicit `else` on their dispatch. Since both are generators, the error surfaces on first consumption, not at call time — tests must wrap the call in `list()`. `is_printable_ascii` is the deliberate exception: it returns `False` for the wide encodings because those are handled by `iter_chars`, not by it.
- **`include_ws` is keyword-only** across `encodings.py`, matching `scan()`'s pre-existing keyword-only signature. This was chosen over globally ignoring ruff's `FBT001`/`FBT002`.
- **The 100% coverage gate lives in `[tool.pytest.ini_options] addopts`, not in the CI step**, so `ci.yml` stays byte-identical across the project family (design.md A2).
- **Input files are memory-mapped, one at a time.** `open_source()` yields an `mmap`-backed `memoryview` that is released when its `with` block exits — so nothing may hold a slice of `source.data` past the block, or closing the map raises `BufferError` (the broken-pipe test is parametrized over both scan paths to guard this). The view, not the bare `mmap`, is passed on because `mmap` iterates as one-byte `bytes` rather than `int`. Empty files are `read()` instead (mmap rejects them, and `/proc`-style files report size 0); stdin is always read whole, since a pipe cannot be mapped (#5).
- **`-d` follows GNU `strings` on well-formed objects, including its quirks.** A section is scanned if BFD would flag it ALLOC, LOAD and HAS_CONTENTS, so code is included, and each format module encodes BFD's rule for that format. Like GNU, a section whose bytes lie outside the file is skipped and the rest are scanned. On malformed input we deliberately don't chase BFD's acceptance rules (it rejects objects with, say, truncated relocations or unknown load commands, and accepts an oversized `sizeofcmds`), so the two can pick different fallbacks there. The README describes `-d`'s behavior rather than promising GNU parity for exactly this reason; don't add a parity claim that needs a malformed-input caveat. What's guaranteed is safety: each parser returns `None` for data that isn't its format or whose header or load commands are damaged, and never raises, so bounds are checked explicitly rather than by catching `struct.error`. `data_ranges` also returns `None` when no section qualifies, because GNU falls back to the whole file then. Fat Mach-O and archives are `None` too: BFD opens them as archives, not objects. `-d` is ignored for stdin, as in GNU. The CLI scans each range from its own slice of the mapped file and releases it with `with`, per the mmap note above. Verify behavior changes against GNU `strings -d -t d` (Homebrew `binutils` understands Mach-O).
- **Scanning is the hot path.** For the ASCII encodings `iter_chars` builds a 256-entry printability table from `is_printable_ascii` once per call and maps it over the data, keeping the per-byte loop in C (#31) — do not reintroduce a per-byte Python call there. The wide path still calls its predicate per character; its bottleneck is the `int.from_bytes` slice, not the predicate. Be wary of adding per-byte work.

## Workflow

- Every feature, fix, or other change gets its own branch and pull request — no direct commits to main.
- Commits must be atomic and follow Conventional Commits (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `deps`): one logical change per commit.
- PRs that resolve an issue reference it with `Closes #N` so it closes automatically on merge.
- **PRs are merged with a merge commit** — never squashed or rebased. Both break stacked PRs, and this project family works in stacks.
- **Keep `CHANGELOG.md` release-ready.** Any user-facing change adds a bullet under `## [Unreleased]` in the same PR (internal-only refactors, CI, test, and docs changes are exempt). Entries follow the existing Keep a Changelog style — grouped under `### Added`/`### Changed`/`### Fixed`/`### Removed`, one line each, ending with the PR ref `(#N)`.
- **Releases are automated and notes come from the changelog — never hand-written commit dumps.** The CD workflow publishes to PyPI when a version bump lands on `main`, then publishes a GitHub release whose body is that version's `CHANGELOG.md` section (extracted between its `## [x.y.z]` heading and the next; it fails the release if the section is missing). Cutting a release is a `chore: release vX.Y.Z` PR that bumps the version and renames `## [Unreleased]` to `## [X.Y.Z] - <date>` (adding a fresh empty `## [Unreleased]` and updating the compare links). See CONTRIBUTING.md → Releasing.

## Code Style

- Google-style docstrings (enforced by ruff).
- Line length: 88 chars.
- Ruff `select = ["ALL"]` with a pragmatic, curated set of ignores (see `pyproject.toml`).
- Tests are exempt from docstring and type-annotation rules, and from `FBT001` since parametrized signatures take booleans positionally.
- Prefer comments that explain *why* code does something, not *what* it does.

## Testing Notes

The testing conventions — parametrized tables, `make_data`, and the two CLI test layers — are documented once, in CONTRIBUTING.md → Testing. Read that rather than a paraphrase here.

The one thing worth repeating: subprocess CLI tests are invisible to coverage, so a new branch in `cli.py` needs an in-process test to satisfy the gate.
