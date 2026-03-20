# Build Your Own `strings` Utility in Python

The Unix `strings` utility is a simple but powerful tool: given any binary file,
it finds and prints every sequence of printable characters long enough to be
interesting. Reverse engineers use it to extract human-readable text from
executables, malware analysts use it to find embedded URLs and config strings,
and developers use it to inspect compiled artifacts without a disassembler.

In this project, you'll build `sillystrings` — a pure-Python, stdlib-only
reimplementation of `strings`. By the end, you'll have a fully tested
command-line tool with ≥ 90% coverage, behavioral parity with GNU `strings` on
all common flags, and a clean src-layout project built with modern Python
tooling.

Along the way, you'll work with raw bytes using `memoryview` and `bytearray`,
design a clean three-module architecture with strict separation of concerns, and
build a full `pytest` suite including integration tests against a real CLI.

---

## Prerequisites

Before diving in, make sure you're comfortable with:

- Python 3.11+ — this project uses `X | Y` union syntax and `match` statements
- Basic `pytest` — writing test functions and using fixtures
- The command line — running tools, redirecting output

You'll be using these tools throughout:

- **uv** — package and project management
- **ruff** — linting and formatting
- **ty** — type checking

---

## Setting Up the Project

### Verifying Your Tools

Start by confirming your toolchain is ready:

```
uv --version
ruff --version
ty --version
```

If anything is missing, install it:

```
curl -LsSf https://astral.sh/uv/install.sh | sh   # installs uv
uv tool install ruff
uv tool install ty
```

Also verify you're on Python 3.11 or later — the `X | Y` union type syntax
used throughout this project requires it:

```
python3 --version
```

### Scaffolding the Project

`uv init --lib` creates a src-layout project for you automatically, which is
exactly what you want:

```
uv init --lib sillystrings && cd sillystrings
uv add --dev pytest pytest-cov
mkdir -p tests scripts
touch src/sillystrings/scanner.py src/sillystrings/encodings.py src/sillystrings/cli.py
```

Now replace the generated `pyproject.toml` with the full version below — it
adds the build system config, ruff rules, and pytest settings you'll need:

```toml
[project]
name = "sillystrings"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
sillystrings = "sillystrings.cli:main"

[dependency-groups]
dev = ["pytest>=8", "pytest-cov>=5"]

[build-system]
requires = ["uv_build"]
build-backend = "uv_build"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=sillystrings --cov-report=term-missing"

[tool.ruff]
line-length = 88
target-version = "py311"
src = ["src"]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "F",   # pyflakes
    "I",   # isort
    "UP",  # pyupgrade
    "B",   # flake8-bugbear
    "SIM", # flake8-simplify
    "ANN", # annotations
]

[tool.ruff.format]
quote-style = "double"

[tool.ty]
# No config needed for a stdlib-only project
```

> **Note:** The `src = ["src"]` setting in `[tool.ruff]` tells ruff's isort
> where to find first-party imports. Without it, ruff may misclassify
> `sillystrings` imports as third-party and sort them incorrectly.

Commit everything to initialise the repo:

```
git init && git add . && git commit -m "init"
```

### Creating the Smoke Test Fixtures

The project includes a script that copies a real binary and runs `strings` on it
to capture expected output. You'll use this to verify `sillystrings` produces
matching results against GNU `strings` on a real-world file.

```
python scripts/make_fixtures.py
```

The [full source of `make_fixtures.py`](#scriptsmake_fixturespy) is in the Reference section. It creates `fixtures/tool.bin`
and a set of expected output files for different minimum string lengths —
`expected_n4.txt`, `expected_n6.txt`, `expected_n10.txt`, and `expected_n20.txt`.
These files are local-only — don't commit them.

---

## Understanding `strings`

Before writing a line of code, it's worth understanding exactly what `strings`
does and which parts of it you'll implement.

At its core, `strings` walks through a binary file byte by byte. When it finds a
sequence of printable characters at least N bytes long (default: 4), it prints
that sequence. Everything else — compressed data, machine code, raw integers —
is silently ignored.

Here's what the most common flags do:

| Flag | What it controls |
|---|---|
| `-n MIN` | Minimum string length (default: 4) |
| `-t x` / `-t d` / `-t o` | Print byte offset before each string (hex/decimal/octal) |
| `-e s` / `-e S` / `-e l` / `-e b` | Character encoding to scan for |
| `-w` | Include whitespace characters (`\t`, `\n`, `\r`) in strings |
| `-f` | Prefix each result with the source filename |
| `-a` | Scan entire file (already the default in GNU strings; a no-op here) |

### What You'll Implement

You're aiming for behavioral parity with GNU `strings` on the common flags above.
Two areas are deliberately out of scope:

**ELF/PE section-aware scanning** — some versions of `strings` can limit their
scan to specific sections of an ELF or PE binary. This is complex to implement
and the whole-file scan (the default) covers the vast majority of real-world use.

**32-bit encodings** (`-e L`, `-e B`) — GNU `strings` supports 32-bit
little-endian and big-endian character encodings. These are extremely rare in
practice and would add significant complexity for very little benefit.

### What "Printable" Means

There's no stdlib function that matches GNU `strings`' definition of printable —
`str.isprintable()` exists but uses Unicode's much broader definition, which
isn't what you want. You'll implement your own, and the rules are simple:

| Encoding flag | Printable bytes | Notes |
|---|---|---|
| `-e s` (7-bit ASCII, default) | 0x20–0x7E | Space through tilde |
| `-e S` (8-bit) | 0x20–0x7E + 0x80–0xFF | Adds high bytes |
| `-e l` (UTF-16 little-endian) | ASCII chars as 2-byte LE pairs | `b"h\x00"` = `'h'` |
| `-e b` (UTF-16 big-endian) | ASCII chars as 2-byte BE pairs | `b"\x00h"` = `'h'` |

Note that `0x7F` (the DEL character) is excluded in every mode despite sitting
between the printable ranges. With `-w`, the whitespace characters `\t` (0x09),
`\n` (0x0A), and `\r` (0x0D) are also included.

---

## Designing the Architecture

Before writing any code, spend a few minutes with the design. There are three
modules with a strict one-way dependency:

```
cli.py  →  scanner.py  →  encodings.py
```

### `encodings.py` — All Byte-Level Logic

This module owns everything that touches individual bytes: what "printable"
means for each encoding mode, and how to step through the data one logical
character at a time. It exposes two functions:

```python
def is_printable(byte: int, encoding: str, include_ws: bool = False) -> bool:
    """Return True if this byte is printable in the given encoding mode."""

def iter_chars(
    data: bytes | memoryview,
    encoding: str,
    include_ws: bool = False,
) -> Iterator[tuple[int, bool]]:
    """Yield (byte_offset, is_printable) for each logical character position."""
```

The key insight behind `iter_chars` is that it hides byte-width from its
callers. For 1-byte encodings (`'s'`, `'S'`), it steps one byte at a time and
yields one `(offset, bool)` per byte. For UTF-16 encodings (`'l'`, `'b'`), it
steps two bytes at a time and yields one `(offset, bool)` per pair. `scanner.py`
never needs to know which encoding is in use.

### `scanner.py` — Pure Scanning Logic

This module contains one public function, `scan()`, which is a generator:

```python
def scan(
    data: bytes | memoryview,
    *,
    min_length: int = 4,
    encoding: str = "s",
    include_whitespace: bool = False,
) -> Iterator[tuple[int, str]]:
    """Yield (byte_offset, string) for each printable run in data."""
```

Crucially, `scan()` has **no I/O and no knowledge of argparse**. It takes raw
bytes and yields results. This design decision makes unit testing trivial — you
can call `list(scan(b"\x00hello\x00"))` directly in a test without touching the
filesystem or the CLI at all.

### `cli.py` — Argument Parsing and Output

`cli.py` exposes a single `main()` function. Its job is to parse arguments with
`argparse`, open files, call `scan()`, and format the results for output. No
scanning logic belongs here — it's pure glue.

### Your Project Layout

Here's what the finished project looks like on disk:

```
sillystrings/
├── src/
│   └── sillystrings/
│       ├── __init__.py
│       ├── encodings.py     # is_printable(), iter_chars()
│       ├── scanner.py       # scan(), _scan_utf16()
│       └── cli.py           # main(), build_parser(), format_offset()
├── tests/
│   ├── conftest.py
│   ├── test_encodings.py
│   ├── test_scanner.py
│   └── test_cli.py
├── scripts/
│   └── make_fixtures.py
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## Part 1: Building the Core

Your goal here is a working, fully-tested implementation. Work through the steps
in order — each module builds on the last, and writing tests alongside each
module keeps the feedback loop tight.

### Step 1: Write `conftest.py`

Start with the shared test fixture. This factory function lets any test create
a binary file from a list of byte segments without touching the real filesystem:

```python
# tests/conftest.py
import pytest
from collections.abc import Callable
from pathlib import Path


@pytest.fixture
def make_binary(tmp_path: Path) -> Callable[[list[bytes]], Path]:
    def _make(segments: list[bytes]) -> Path:
        p = tmp_path / "test.bin"
        p.write_bytes(b"".join(segments))
        return p
    return _make
```

> **Tip:** `tmp_path` is a built-in pytest fixture that provides a fresh
> temporary directory unique to each test. You don't need to import or declare
> it — pytest injects it automatically.

### Step 2: Implement and Test `encodings.py`

Write `is_printable()` first, then `iter_chars()`. The full implementations are
in the Reference section. As you write them, build `test_encodings.py` in
parallel.

Key cases to cover in `test_encodings.py`:

- **`is_printable` boundaries:** `0x1F` (not printable), `0x20` (space, printable), `0x7E` (tilde, printable), `0x7F` (DEL, not printable)
- **`is_printable` in `'S'` mode:** `0x7F` still excluded, `0x80` included, `0xFF` included
- **`iter_chars` in `'s'` mode:** yields one `(offset, bool)` per byte, offsets are sequential
- **`iter_chars` in `'l'` (UTF-16 LE):** `b"h\x00i\x00"` → offsets 0 and 2, both printable
- **`iter_chars` in `'b'` (UTF-16 BE):** `b"\x00h\x00i"` → offsets 0 and 2, both printable
- **UTF-16 with odd-length data:** last byte silently ignored (the `len - 1` bound handles this naturally)
- **UTF-16 non-ASCII codepoint:** `b"\x00\x41"` in LE has `low=0x00, high=0x41` — high byte is non-zero, so it represents U+4100, not `'A'`; not printable

### Step 3: Implement and Test `scanner.py`

With `encodings.py` solid, `scanner.py` can focus entirely on the accumulator
logic without worrying about bytes. The full implementation is in the Reference
section — read the walkthrough there before coding.

> **Note:** Write the end-of-file test case *first*. It's the most commonly
> forgotten edge case: a printable run that ends at the last byte of the file
> has no trailing non-printable byte to trigger the flush. If you forget the
> post-loop flush, this test will catch it immediately.

Key cases to cover in `test_scanner.py`:

- **Basic extraction:** `b"\x00hello\x00"` → `[(1, "hello")]`
- **String at offset 0:** `b"hello\x00"` → `[(0, "hello")]`
- **String at end of file:** `b"\x00hello"` → `[(1, "hello")]` ← write this first
- **Too short:** `b"\x00hi\x00"` with `min_length=4` → `[]`
- **Exact minimum length:** `b"\x00abcd\x00"` with `min_length=4` → `[(1, "abcd")]`
- **Multiple strings:** `b"hello\x00world"` → `[(0, "hello"), (6, "world")]`
- **All printable:** `b"hello"` → `[(0, "hello")]`
- **All non-printable:** `b"\x00\x01\x02"` → `[]`
- **Offset accuracy:** construct a binary with known gaps and assert exact offsets
- **UTF-16 LE mode:** `"hi".encode("utf-16-le")` with `encoding="l"` → `[(0, "hi")]`
- **8-bit mode:** bytes above `0x7F` should appear in strings when `encoding="S"`

### Step 4: Implement and Test `cli.py`

The full implementation of `cli.py` is in the Reference section. When writing
integration tests, use a small `run()` helper to keep the tests readable:

```python
# tests/test_cli.py
import subprocess
from pathlib import Path


def run(*args: str, data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    cmd = ["uv", "run", "sillystrings", *args]
    return subprocess.run(cmd, input=data, capture_output=True)


def test_basic(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00hello world\x00")
    result = run(str(f))
    assert result.returncode == 0
    assert b"hello world" in result.stdout


def test_min_length(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00hello\x00")
    assert b"hello" not in run(str(f), "-n", "6").stdout
    assert b"hello" in run(str(f), "-n", "5").stdout


def test_offset_hex(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00\x00\x00hello\x00")
    assert b"3" in run(str(f), "-t", "x").stdout


def test_stdin() -> None:
    result = run("-", data=b"\x00hello world\x00")
    assert b"hello world" in result.stdout


def test_missing_file() -> None:
    result = run("nonexistent.bin")
    assert result.returncode != 0


def test_multiple_files(tmp_path: Path) -> None:
    f1 = tmp_path / "a.bin"
    f2 = tmp_path / "b.bin"
    f1.write_bytes(b"\x00hello\x00")
    f2.write_bytes(b"\x00world\x00")
    result = run(str(f1), str(f2))
    assert b"a.bin" in result.stdout
    assert b"b.bin" in result.stdout
```

### Step 5: Run the Suite

```
uv run pytest
```

Aim for green tests and ≥ 90% coverage before moving on.

---

## Part 2: Polish, Edge Cases, and Verification

You have a working tool. This part is about making it solid.

### Reviewing Coverage

Run pytest with an HTML coverage report so you can see exactly which lines
aren't covered:

```
uv run pytest --cov-report=html
open htmlcov/index.html
```

Common gaps to look for: stdin handling, the `-f` flag, the `-w` whitespace
mode, the exact boundary between `min_length` and `min_length - 1`, and any
error paths in `cli.py`.

### Edge Cases Worth Hardening

These are the scenarios most likely to reveal subtle bugs:

- **Empty file:** `scan(b"")` should yield nothing without raising
- **All non-printable:** no output, no errors
- **Very large `min_length`:** larger than any run in the file → no output
- **Single-character file:** both printable and non-printable variants
- **UTF-16 with exactly one byte:** should yield nothing (can't form a pair)
- **8-bit mode with high bytes adjacent to low bytes:** ensure the accumulator doesn't mix codecs

### Smoke Testing Against Real `strings`

Run your implementation against the tool binary across all four minimum lengths
and diff the output against what GNU `strings` produced:

```
for n in 4 6 10 20; do
  echo "--- n=$n ---"
  diff <(uv run sillystrings -n $n fixtures/tool.bin) fixtures/expected_n${n}.txt
done
```

A clean diff on all four lengths means your implementation matches GNU `strings`
exactly on a real-world binary across a meaningful range of parameters. Any
differences are worth investigating.

### Final Quality Pass

```
uv run ruff check . --fix && uv run ruff format . && uv run ty check
```

Fix anything that comes up, then make a final commit:

```
git add . && git commit -m "complete implementation"
git tag v0.1.0
```

---

---

# Reference

---

## `encodings.py` — Full Implementation

### `is_printable()`

```python
# src/sillystrings/encodings.py
from typing import Literal

Encoding = Literal["s", "S", "l", "b"]


def is_printable(byte: int, encoding: str, include_ws: bool = False) -> bool:
    """Return True if `byte` is printable for the given single-byte encoding.

    Only meaningful for 's' and 'S' modes. For UTF-16 modes ('l', 'b'),
    printability is determined by the byte pair inside iter_chars().
    """
    if include_ws and byte in (0x09, 0x0A, 0x0D):  # \t \n \r
        return True
    if encoding == "s":
        return 0x20 <= byte <= 0x7E
    if encoding == "S":
        return (0x20 <= byte <= 0x7E) or (0x80 <= byte <= 0xFF)
    return False
```

Printability boundaries to keep in mind:
- `0x20` = space — first printable character
- `0x7E` = `~` — last printable ASCII character
- `0x7F` = DEL — excluded in every mode, despite sitting between `0x7E` and `0x80`
- `0x80`–`0xFF` — included only in `'S'` (8-bit) mode

### `iter_chars()`

```python
from collections.abc import Iterator


def iter_chars(
    data: bytes | memoryview,
    encoding: str,
    include_ws: bool = False,
) -> Iterator[tuple[int, bool]]:
    """Yield (byte_offset, is_printable) for each logical character position."""
    if encoding in ("s", "S"):
        for i, byte in enumerate(data):
            yield i, is_printable(byte, encoding, include_ws)
    elif encoding == "l":   # UTF-16 little-endian: low byte first
        for i in range(0, len(data) - 1, 2):
            low, high = data[i], data[i + 1]
            yield i, (high == 0x00 and 0x20 <= low <= 0x7E)
    elif encoding == "b":   # UTF-16 big-endian: high byte first
        for i in range(0, len(data) - 1, 2):
            high, low = data[i], data[i + 1]
            yield i, (high == 0x00 and 0x20 <= low <= 0x7E)
```

For UTF-16, a character is printable if it encodes an ASCII codepoint: one byte
holds a value in `0x20`–`0x7E` and the other byte is `0x00`. Anything else is
treated as non-printable and breaks the current string run.

---

## `scanner.py` — Full Implementation

### Understanding the Accumulator Pattern

`scan()` works by walking through `(offset, is_printable)` pairs from
`iter_chars()` and maintaining a running accumulator of the current printable
run. When it encounters a non-printable character, it flushes the accumulator
if it's long enough, then clears it and starts over.

A `bytearray` is used for 1-byte encodings because it can be cleared in-place
with `acc.clear()`, avoiding a heap allocation on every non-printable byte.
For UTF-16 encodings, each character is two bytes wide, so you can't simply
accumulate raw bytes and decode later — instead, decoded characters are
accumulated in a `list[str]`.

There's one subtlety that trips people up: **the post-loop flush**. A printable
run that ends at the very last byte of the file never encounters a non-printable
character to trigger the flush inside the loop. You must flush again after the
loop ends. Write a test for this case first.

> **Note:** In `'S'` (8-bit) mode, use `acc.decode("latin-1")` instead of
> `acc.decode("ascii")`. The `ascii` codec raises `UnicodeDecodeError` on any
> byte above `0x7F`, but `latin-1` maps all 256 byte values directly to Unicode
> codepoints without error.

### Full Implementation

```python
# src/sillystrings/scanner.py
from collections.abc import Iterator

from sillystrings.encodings import iter_chars


def scan(
    data: bytes | memoryview,
    *,
    min_length: int = 4,
    encoding: str = "s",
    include_whitespace: bool = False,
) -> Iterator[tuple[int, str]]:
    """Yield (byte_offset, string) for each printable run in data."""
    if encoding in ("l", "b"):
        yield from _scan_utf16(
            data,
            min_length=min_length,
            encoding=encoding,
            include_whitespace=include_whitespace,
        )
        return

    codec = "latin-1" if encoding == "S" else "ascii"
    acc = bytearray()
    acc_start = 0

    for offset, printable in iter_chars(data, encoding, include_whitespace):
        if printable:
            if not acc:
                acc_start = offset
            acc.append(data[offset])
        else:
            if len(acc) >= min_length:
                yield acc_start, acc.decode(codec)
            acc.clear()

    if len(acc) >= min_length:
        yield acc_start, acc.decode(codec)


def _scan_utf16(
    data: bytes | memoryview,
    *,
    min_length: int,
    encoding: str,
    include_whitespace: bool,
) -> Iterator[tuple[int, str]]:
    acc_chars: list[str] = []
    acc_start = 0

    for offset, printable in iter_chars(data, encoding, include_whitespace):
        if printable:
            if not acc_chars:
                acc_start = offset
            # For LE: the ASCII codepoint is the low byte at data[offset]
            # For BE: the ASCII codepoint is the low byte at data[offset + 1]
            low = data[offset] if encoding == "l" else data[offset + 1]
            acc_chars.append(chr(low))
        else:
            if len(acc_chars) >= min_length:
                yield acc_start, "".join(acc_chars)
            acc_chars.clear()

    if len(acc_chars) >= min_length:
        yield acc_start, "".join(acc_chars)
```

---

## `cli.py` — Full Implementation

```python
# src/sillystrings/cli.py
import argparse
import sys

from sillystrings.scanner import scan


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sillystrings",
        description="Print printable strings found in binary files.",
    )
    p.add_argument(
        "files",
        metavar="FILE",
        nargs="*",                     # zero or more; empty list → read stdin
        type=argparse.FileType("rb"),  # opens the file in binary mode for you
    )
    p.add_argument(
        "-n", "--bytes",
        dest="min_length",
        type=int,
        default=4,
        metavar="MIN",
        help="minimum string length (default: 4)",
    )
    p.add_argument(
        "-t", "--radix",
        choices=("d", "o", "x"),
        default=None,
        help="print byte offset before each string: d=decimal, o=octal, x=hex",
    )
    p.add_argument(
        "-e", "--encoding",
        choices=("s", "S", "l", "b"),
        default="s",
        help="s=7-bit ASCII (default), S=8-bit, l=UTF-16 LE, b=UTF-16 BE",
    )
    p.add_argument("-w", "--include-all-whitespace", action="store_true")
    p.add_argument(
        "-a", "--all",
        action="store_true",
        help="scan entire file (already the default; accepted for compatibility)",
    )
    p.add_argument("-f", "--print-file-name", action="store_true")
    return p


def format_offset(offset: int, radix: str | None) -> str:
    match radix:
        case "d": return f"{offset:7d} "
        case "o": return f"{offset:7o} "
        case "x": return f"{offset:7x} "
        case _:   return ""


def main() -> None:
    args = build_parser().parse_args()
    sources: list[tuple[str, bytes]]
    if not args.files:
        sources = [("<stdin>", sys.stdin.buffer.read())]
    else:
        sources = [(f.name, f.read()) for f in args.files]
        for f in args.files:
            f.close()
    multiple = len(sources) > 1
    for name, data in sources:
        for offset, string in scan(
            data,
            min_length=args.min_length,
            encoding=args.encoding,
            include_whitespace=args.include_all_whitespace,
        ):
            prefix = f"{name}: " if (multiple or args.print_file_name) else ""
            print(f"{prefix}{format_offset(offset, args.radix)}{string}")
```

> **Note:** `argparse.FileType("rb")` opens files during `parse_args()`, so
> error messages for missing files come from argparse rather than your own code.
> That's a reasonable tradeoff for a project of this size.

---

## `scripts/make_fixtures.py`

```python
#!/usr/bin/env python3
"""Generate fixtures/ for smoke testing sillystrings against real strings output.

Usage: python scripts/make_fixtures.py
Requires: the `strings` utility to be on PATH.

Generates:
  fixtures/tool.bin              — binary to scan
  fixtures/expected_n4.txt       — strings -n 4 output
  fixtures/expected_n6.txt       — strings -n 6 output
  fixtures/expected_n10.txt      — strings -n 10 output
  fixtures/expected_n20.txt      — strings -n 20 output
"""
import shutil
import subprocess
import sys
from pathlib import Path

FIXTURES    = Path(__file__).parent.parent / "fixtures"
BINARY      = FIXTURES / "tool.bin"
MIN_LENGTHS = [4, 6, 10, 20]

# The Python interpreter is often stripped and produces no strings output.
# uv, ruff, and ty are unstripped Rust binaries with plenty of readable strings.
CANDIDATES = ["uv", "ruff", "ty"]


def find_candidate() -> tuple[str, str]:
    """Return (name, path) for the first candidate binary found on PATH."""
    for name in CANDIDATES:
        path = shutil.which(name)
        if path:
            return name, path
    print(f"error: none of {CANDIDATES} found on PATH", file=sys.stderr)
    sys.exit(1)


def run_strings(strings_bin: str, min_length: int) -> str:
    """Run strings with the given minimum length and return stdout."""
    result = subprocess.run(
        [strings_bin, "-n", str(min_length), str(BINARY)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def main() -> None:
    FIXTURES.mkdir(exist_ok=True)

    _name, path = find_candidate()

    if BINARY.exists():
        print(f"skipping {BINARY} (already exists)")
    else:
        shutil.copy2(path, BINARY)
        print(f"created {BINARY} (copied from {path})")

    strings_bin = shutil.which("strings")
    if not strings_bin:
        print("error: `strings` not found on PATH — install binutils", file=sys.stderr)
        sys.exit(1)

    for n in MIN_LENGTHS:
        expected = FIXTURES / f"expected_n{n}.txt"
        if expected.exists():
            print(f"skipping {expected} (already exists)")
        else:
            output = run_strings(strings_bin, n)
            expected.write_text(output, encoding="utf-8")
            print(f"created {expected} ({output.count(chr(10))} lines)")


if __name__ == "__main__":
    main()
```

---

## Python Patterns Quick Reference

### `bytearray` — Mutable Bytes

`bytearray` is a mutable sequence of bytes. The key advantage over `bytes` is
that you can clear it in-place, which matters in a tight loop:

```python
acc = bytearray()
acc.append(104)       # 'h'
acc.append(105)       # 'i'
acc.decode("ascii")   # → "hi"
acc.decode("latin-1") # same result; also handles bytes 0x80–0xFF
acc.clear()           # resets in-place — no new allocation
len(acc)              # → 0
```

### `memoryview` — Zero-Copy Buffer Access

When you slice a `bytes` object with `data[i:j]`, Python allocates a brand new
`bytes` object and copies the data into it. For a 50 MB binary, doing this on
every iteration adds up. `memoryview` gives you a view into the original buffer
with no copying:

```python
raw = Path("mybinary").read_bytes()
mv = memoryview(raw)

mv[0]        # int — same as raw[0], no copy
mv[10:20]    # memoryview slice — still no copy
list(mv[:4]) # → [104, 101, 108, 108]  (ints, 0–255)
```

Iterating a `memoryview` of bytes yields integers just like iterating `bytes`,
so `for i, byte in enumerate(data)` works identically whether `data` is `bytes`
or `memoryview`.

> **Note:** You can't call `.decode()` on a `memoryview` slice directly. In
> this project that's a non-issue because you always decode the `bytearray`
> accumulator, not the input data.

### REPL Sanity Checks

```python
# UTF-16 encoding
"hi".encode("utf-16-le")   # → b'h\x00i\x00'  (low byte first)
"hi".encode("utf-16-be")   # → b'\x00h\x00i'  (high byte first)

# Printability boundaries
chr(0x20)  # → ' '    (space — first printable)
chr(0x7E)  # → '~'    (tilde — last printable ASCII)
chr(0x7F)  # → '\x7f' (DEL — not printable in any mode)
chr(0x80)  # → '\x80' (printable in 'S' mode only)

# memoryview iterates as ints
list(memoryview(b"hi"))  # → [104, 105]
```

---

## Type Annotation Quick Reference

```python
from collections.abc import Iterator
from typing import Literal

# Constrain to specific string values — ty catches typos at call sites
Encoding = Literal["s", "S", "l", "b"]
Radix    = Literal["d", "o", "x"]

# Union types (Python 3.10+ syntax)
def scan(data: bytes | memoryview) -> Iterator[tuple[int, str]]: ...
def foo(x: int | None = None) -> None: ...

# Generator functions — annotate return as Iterator, not Generator
def scan(data: bytes) -> Iterator[tuple[int, str]]:
    yield 0, "hello"  # Python recognises this as a generator automatically

# Prefer collections.abc over typing in Python 3.9+
from collections.abc import Iterator  # correct for 3.9+
from typing import Iterator           # legacy, still works
```

---

## Tool Quick Reference

### `uv`

```bash
uv run pytest              # run tests in the project venv
uv run python              # open a REPL in the project venv
uv run sillystrings        # run the CLI entry point
uv add --dev pytest        # add a dev dependency
uv sync                    # install all dependencies from the lockfile
uv pip list                # list installed packages
```

Always commit `uv.lock`. It pins the exact versions of all dependencies
(including transitive ones) so that anyone cloning the repo gets the same
environment you tested with.

### `ruff`

```bash
uv run ruff check . --fix          # lint and auto-fix
uv run ruff format .               # format in place
uv run ruff check . --fix && uv run ruff format .   # do both at once
uv run ruff format --check .       # check formatting without writing (CI-style)
```

Common rule codes you'll encounter:

| Code | Meaning | Fix |
|---|---|---|
| `E501` | Line too long | Wrap the line |
| `F401` | Unused import | Remove it |
| `F841` | Unused variable | Remove or rename to `_` |
| `I001` | Imports not sorted | `--fix` handles this |
| `UP006` / `UP007` | Use `list` / `X \| Y` instead of `List` / `Optional` | `--fix` handles these |
| `ANN001` | Missing arg annotation | Add the type |
| `ANN201` | Missing return annotation | Add `-> ReturnType` |
| `B007` | Loop variable unused | Rename to `_` |
| `SIM108` | Ternary preferred over if/else block | Collapse to one line |

### `ty`

```bash
uv run ty check                    # check all files
uv run ty check src/sillystrings/  # check a specific directory
```

Common errors on this project:

| Error | Fix |
|---|---|
| `"memoryview" not assignable to "bytes"` | Widen the annotation to `bytes \| memoryview` |
| `Return type "Iterator[...]" incompatible` | Add `from collections.abc import Iterator` |
| `Cannot access attribute "read" on "str"` | You passed a filename string where a file object was expected |

Suppress a genuine false positive sparingly:
```python
result = some_call()  # type: ignore[attr-defined]
```
