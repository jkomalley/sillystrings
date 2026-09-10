# Contributing to sillystrings

Thanks for your interest in improving `sillystrings`. This guide covers
everything you need to get set up and land a change. For *usage*, see the
[README](README.md).

## Ways to contribute

- **Report a bug** or **request a feature** by [opening an issue](https://github.com/jkomalley/sillystrings/issues).
- **Submit a pull request** for a fix or improvement.

For anything large or behavior-changing, please open an issue to discuss the
approach before investing time in a PR.

## Development setup

**Prerequisites:** Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/jkomalley/sillystrings.git
cd sillystrings
just install               # uv sync + pre-commit install
```

Or without `just`:

```bash
uv sync                    # create the venv and install all dependencies
uv run pre-commit install  # enable the git hooks
```

## Project layout

The package uses a `src/` layout. Each module has a single, focused
responsibility:

| Module | Responsibility |
| --- | --- |
| `encodings.py` | The encoding vocabulary (`Encoding`, `ASCII_ENCODINGS`, `UTF16_ENCODINGS`), the per-byte printability predicates, and `iter_chars` — which walks a buffer yielding `(offset, printable)`. |
| `scanner.py` | `scan()` — the public API. Dispatches to the `_scan_ascii` / `_scan_utf16` accumulators, which group runs of printable characters into strings meeting the minimum length. |
| `cli.py` | The `sillystrings` command-line entry point: argparse wiring, offset formatting, and stdin/file input handling. |
| `__version__.py` | The installed version, read from package metadata. |

The encoding letters (`s`, `S`, `l`, `b`) are defined **once**, in
`encodings.py`. `cli.py` derives its `-e` choices from `get_args(Encoding)`, so
the flag cannot drift from what `scan()` accepts — don't reintroduce a literal
list of encodings anywhere.

## Running checks

The repo uses [`just`](https://github.com/casey/just) as a task runner. Run
everything before pushing:

```bash
just check      # format-check + lint-check + typecheck + test-cov
```

Or run individual tasks:

```bash
just format     # ruff format
just lint       # ruff check --fix
just typecheck  # ty check src/
just test       # pytest
just test-cov   # pytest with the 100% coverage gate
just run --help # drive the CLI locally
```

Each task maps to a plain `uv run …` command, so you can run them directly if
you'd rather not install `just`.

## Coding standards

- **Style & linting:** [`ruff`](https://docs.astral.sh/ruff/) with nearly all
  rules enabled (see `pyproject.toml` for the pragmatic exceptions). Run
  `just format` and `just lint` before committing.
- **Type checking:** the codebase is fully typed; `just typecheck` must pass.
- **Docstrings:** Google-style, on every public function and class.
- **Comments:** explain *why*, not *what*. Lean toward documenting non-obvious
  decisions; skip comments that merely restate the code.
- **Line length:** 88 characters.

### Testing

- **100% branch coverage is required.** The gate lives in
  `[tool.pytest.ini_options] addopts`, so it applies to every `pytest` run, not
  just CI. Every new branch needs a test.
- Scanner behavior is covered by parametrized tables in `tests/test_scanner.py`
  and `tests/test_encodings.py`. Add a row rather than a new test function when
  the case fits the existing table, and keep the comment above the tuple so the
  row stays on one line.
- Build test inputs with `make_data` from `tests/conftest.py`, which encodes
  string segments for the target encoding and appends raw `bytes` segments
  as-is — that is how to construct odd-length or deliberately malformed buffers.
- CLI tests come in two layers: subprocess smoke tests through the `run` helper,
  which confirm the installed entry point works, and in-process tests that call
  `cli.py` directly. Only the second layer is visible to coverage, so a new
  branch in `cli.py` needs an in-process test.

## Pull requests

- Branch off `main`; one logical change per PR.
- Keep commits atomic — a single coherent change each, not a bundle of unrelated
  edits.
- Follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat`,
  `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `deps`).
- Reference the issue a PR resolves with `Closes #N`.
- Include tests for any new or changed behavior.
- Add a bullet under `## [Unreleased]` in `CHANGELOG.md` for any user-facing
  change. Internal-only refactors, CI, test and docs changes are exempt.
- Make sure `just check` passes cleanly before you open the PR.
- **PRs are merged with a merge commit** — not squashed, not rebased.

CI runs the full check suite against Python 3.11–3.14 on every pull request.

## Releasing

Releases are published to PyPI automatically: the CD workflow fires when CI
passes on `main` and publishes whenever `pyproject.toml`'s version isn't already
on PyPI. So a release is just a version bump merged to `main`.

Choose the bump from the changes since the **last release tag**, not just your
latest work:

```bash
git log "$(git describe --tags --abbrev=0)"..HEAD --oneline
```

Map the conventional-commit types in that range to a [semver](https://semver.org/)
bump and apply it locally:

| Changes since last release | Bump | Command |
| --- | --- | --- |
| Any `feat:` | minor | `just bump-version minor` |
| Only `fix:` / `docs:` / `chore:` | patch | `just bump-version patch` |
| A breaking change (`feat!:`, `BREAKING CHANGE`) | major¹ | `just bump-version major` |

¹ While the project is pre-1.0, breaking changes are released as a **minor**
bump per semver's 0.x convention.

Bumping is a local step — there is deliberately no bump-version workflow, since
pull requests opened with `GITHUB_TOKEN` never trigger workflows and so could
never satisfy required status checks.

Open the bump as its own `chore: release vX.Y.Z` PR that also renames
`## [Unreleased]` to `## [X.Y.Z] - <date>` in `CHANGELOG.md`, adds a fresh empty
`## [Unreleased]`, and updates the compare links at the bottom. The release
notes are extracted from that section, and the release fails if it is missing.

The `version-guard` CI job enforces the bump size: it fails any release PR whose
bump is too small for the commits since the last release (for example, shipping
a `feat:` in a patch). Features merged to `main` without a release accumulate,
so the bump must account for all of them — not just the most recent change.

## License

By contributing, you agree that your contributions are licensed under the
project's [MIT License](LICENSE).
