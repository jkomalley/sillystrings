# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`sillystrings` is a pure-Python reimplementation of the Unix `strings` utility: it extracts printable character sequences from binary files. Python 3.11+, src layout, managed with `uv`, zero runtime dependencies. Published on PyPI.

**GNU binutils `strings` is the reference for all behavior**, not macOS `strings`: flags, defaults, which strings are found, offsets, and output bytes. Check any change that can affect output with `scripts/compare_gnu.py`, which works for any `-e`, against Homebrew `binutils`' GNU `strings` (CONTRIBUTING.md → Verifying `-d` against GNU). The deliberate differences are documented: `-` means stdin, not `-a`, and malformed objects under `-d` (see Key design decisions). An issue or older doc that implies otherwise predates this decision. Check it against GNU before implementing it.

## Commands

Recipes live in the `justfile`; `just` (or `just --list`) prints them with their descriptions. Do not restate their expansions here — that is what rots.

- `just install` — sync the venv and install the git hooks. Run it only in the main checkout, never in a `git worktree`: hooks live in the shared `.git/hooks` and record the installing venv's path, so installing from a worktree breaks commits everywhere once that worktree is removed. In a worktree, `uv sync` is enough.
- `just run --help` — drive the CLI locally
- `just test` / `just test-cov` — the suite without / with the 100% coverage gate (the gate lives in `addopts`; `just test` opts out with `--no-cov`)
- `just format` / `just format-check`, `just lint` / `just lint-check`, `just typecheck`
- `just check` — everything, in the order CI will run it
- `just clean`, `just lock-upgrade`, `just bump-version <part>`

**Run a single test:** `uv run pytest --no-cov tests/test_scanner.py::TestScanner::test_scan -v`. The `--no-cov` is required — the gate in `addopts` fails any partial run.

Note the ruff recipes are scoped to `src/ tests/` while `ruff check .` covers the repo including `scripts/`; both are clean and both must stay that way, since the pre-commit hooks run over every staged file.

## Architecture

The project uses a `src/sillystrings/` layout. Its modules form two strict dependency lines from the CLI — `cli.py` → `scanner.py` → `encodings.py`, and `cli.py` → `formats/` → `formats/common.py`. The format parsers never import the scanner.

- `encodings.py` — The encoding vocabulary and the per-character printability rules. Defines `Encoding` (the `Literal["s", "S", "l", "b", "L", "B"]` alias), the `ASCII_ENCODINGS` tuple and the `WIDE_ENCODINGS` map (encoding → character width and byte order) that both dispatchers switch on, `unsupported_encoding()` for the shared error, the `is_printable_ascii` predicate, `iter_chars()` — which walks a buffer in an ASCII encoding yielding `(offset, printable)` pairs — and `wide_string_pattern()`, which compiles the regex the wide encodings are matched with.
- `scanner.py` — `scan()`, the public API. Dispatches on encoding to `_scan_ascii`, which accumulates runs of printable bytes from `iter_chars` and flushes a trailing run after the loop, or `_scan_wide`, which yields each `wide_string_pattern` match. Both yield `(offset, string)` for every run meeting `min_length`.
- `formats/` — Object file parsers for `-d`. `data_ranges(data)` in `__init__.py` tries each format's `data_sections()` in turn (a new format is one more `_PARSERS` entry) and returns `(offset, size)` file ranges, or `None` meaning "scan the whole file". `macho.py` parses thin Mach-O, `elf.py` parses ELF (both 32/64-bit, either byte order); `common.py` holds the `Section(name, offset, size)` record and the struct helpers both parsers share (`struct_format`, `sizeof`, `unpack`), which read a transcribed struct's per-field format codes.
- `cli.py` — The argparse entry point. Builds the parser, checks every path up front, then opens each source in turn with `open_source()` (a context manager yielding a `Source`), formats offsets by radix, and prints results.

Key design decisions:

- **The encoding letters are defined once, in `encodings.py`.** `cli.py` derives its `-e` choices from `get_args(Encoding)` rather than repeating the list, so the flag cannot drift from what `scan()` accepts. Before this was consolidated the four letters appeared in eight places across four files. Do not reintroduce a literal encoding list.
- **An unsupported encoding raises `ValueError`, it does not yield nothing.** Both `scan()` and `iter_chars()` have an explicit `else` on their dispatch. Since both are generators, the error surfaces on first consumption, not at call time — tests must wrap the call in `list()`. `is_printable_ascii` is the deliberate exception: it returns `False` for the wide encodings because those are matched by `wide_string_pattern`, not by it.
- **`include_ws` is keyword-only** across `encodings.py`, matching `scan()`'s pre-existing keyword-only signature. This was chosen over globally ignoring ruff's `FBT001`/`FBT002`.
- **The 100% coverage gate lives in `[tool.pytest.ini_options] addopts`, not in the CI step**, so `ci.yml` stays byte-identical across the project family (design.md A2).
- **Input files are memory-mapped, one at a time.** `open_source()` yields an `mmap`-backed `memoryview` that is released when its `with` block exits — so nothing may hold a slice of `source.data` past the block, or closing the map raises `BufferError` (the broken-pipe test is parametrized over both scan paths to guard this). The view, not the bare `mmap`, is passed on because `mmap` iterates as one-byte `bytes` rather than `int`. Empty files are `read()` instead (mmap rejects them, and `/proc`-style files report size 0); stdin is always read whole, since a pipe cannot be mapped (#5).
- **`-d` follows GNU `strings` on well-formed objects, including its quirks.** A section is scanned if BFD would flag it ALLOC, LOAD and HAS_CONTENTS, so code is included, and each format module encodes BFD's rule for that format. Like GNU, a section whose bytes lie outside the file is skipped and the rest are scanned. On malformed input we deliberately don't chase BFD's acceptance rules (it rejects objects with, say, truncated relocations or unknown load commands, and accepts an oversized `sizeofcmds`), so the two can pick different fallbacks there. The README describes `-d`'s behavior rather than promising GNU parity for exactly this reason; don't add a parity claim that needs a malformed-input caveat. What's guaranteed is safety: each parser returns `None` for data that isn't its format or whose header, load commands or section headers are damaged, and never raises, so bounds are checked explicitly rather than by catching `struct.error`. `data_ranges` also returns `None` when no section qualifies, because GNU falls back to the whole file then. Fat Mach-O and archives are `None` too: BFD opens them as archives, not objects. `-d` is ignored for stdin, as in GNU. The CLI scans each range from its own slice of the mapped file and releases it with `with`, per the mmap note above. Verify behavior changes with `scripts/compare_gnu.py` against Homebrew `binutils`' GNU `strings`, which understands Mach-O and ELF (CONTRIBUTING.md → Verifying `-d` against GNU).
- **ELF's BFD rule differs from Mach-O's in where "has contents" comes from.** BFD sets HAS_CONTENTS from the type alone (anything but `SHT_NOBITS`), not the offset, so an `SHF_ALLOC` section at offset 0 is scanned. Debug sections are only recognized by name when they lack `SHF_ALLOC`, so `elf.py` never filters on names. What it does mirror, from `bfd_section_from_shdr` and `elf_object_p`: headers BFD makes no section from (`SHT_NULL`, `SHT_SHLIB`, `SHT_SYMTAB_SHNDX`, every `SHT_SYMTAB` except the first one in an `ET_DYN` (BFD makes a section only of the object's first symbol table, and only in a shared object), the name table and the symbol table's strings, relocations it folds into their target in an `ET_REL`); no sections at all when there is no section header table (BFD does not synthesize sections from program headers) or `e_shstrndx` is unusable; `None` for `ET_CORE` (opened as `bfd_core`, not `bfd_object`); and `None` when a section name or any non-empty note can't be read, since BFD reads both while opening the file and rejects it on failure. Extended numbering (`e_shnum == 0`, `e_shstrndx == SHN_XINDEX`) is read from section 0, and any nonzero count is accepted: BFD's internal `SHN_LORESERVE` is `0xffffff00` (`include/elf/internal.h` redefines it), not elf.h's `0xff00`, so don't add an elf.h-based cap. Section names are cut at `NAME_LIMIT` (256) bytes: nothing filters on them, and reading each to its NUL let a damaged, unterminated name table cost quadratic time and memory. Deliberately not mirrored, like Mach-O's malformed-input rules, so don't "fix" these: BFD also rejects an object with `sh_link`/`sh_info` past the table (except x86/SPARC `SHN_BEFORE`/`SHN_AFTER`, which then match several targets ambiguously), symbol or relocation tables with the wrong `sh_entsize`, program headers past EOF, or corrupt section groups, and scans it whole; we scan its sections. The user decided this on #57. A machine's own target also rejects unknown `SHF_ALLOC` section types, but multi-target builds such as Homebrew's then fall back to a generic ELF target that accepts them, as we do. Sections come back in header order; BFD can build one early while resolving a string table's links, which we don't reproduce, but no real file in the verification set hit it.
- **Format definitions are transcribed from the spec, never encoded.** `macho.py` and `elf.py` spell out each `<mach-o/loader.h>` / `<elf.h>` struct as a `NamedTuple` (ELF's keep the header's typedef names, such as `Elf64_Shdr`), field by field in header order with the header's names and a struct code per field. Sizes come from `sizeof()`, not literals. Every constant carries the header's name and cites its `#define`, and every BFD rule cites its binutils file and function. `build_macho` and `build_elf` in `tests/conftest.py` transcribe the same headers **independently**; never make them import from the parsers. `tests/test_macho_constants.py` and `tests/test_elf_constants.py` compile both transcriptions against the real header — the Mach-O one on a Mac only (skipped on CI), the ELF one on Linux only (it runs in CI, and is skipped on a Mac) — so a new struct or constant must be added there too.
- **Scanning is the hot path.** For the ASCII encodings `iter_chars` builds a 256-entry printability table from `is_printable_ascii` once per call and maps it over the data, keeping the per-byte loop in C (#31) — do not reintroduce a per-byte Python call there. The wide encodings are matched by a compiled regex, which also reproduces GNU's rule that strings need not be aligned to the character width (#64); keep the wide path in `re`, not a Python loop. Be wary of adding per-byte work.

## Workflow

- Every feature, fix, or other change gets its own branch and pull request — no direct commits to main.
- Commits must be atomic and follow Conventional Commits (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `deps`): one logical change per commit.
- PRs that resolve an issue reference it with `Closes #N` so it closes automatically on merge.
- **PRs are merged with a merge commit** — never squashed or rebased. Both break stacked PRs, and this project family works in stacks.
- **Bring a PR branch up to date by merging `main` into it, never by rebasing, and never force-push.** Review happens commit by commit, so history already reviewed must not change.
- **CI only runs on PRs that target `main`** (`ci.yml`). A stacked PR whose base is another feature branch gets no CI, so run `just check` locally, and retarget it to `main` once its base merges.
- **To cite the PR number in a CHANGELOG entry, open the PR first**, then add the entry as its own `docs:` commit.
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
