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

## Part 3: Max String Length Limit

macOS `strings` has a hardcoded 1022-character buffer. When a printable run
exceeds that limit, the first 1022 characters are output as a string, and
scanning continues from the very next byte — byte 1023 starts a fresh
accumulator. If it's printable, it begins a new string candidate.

This means a 2050-character run produces three strings: 1022, 1022, and 6.
sillystrings currently has no limit, so it happily produces strings up to ~2M
characters long. Time to fix that.

### Step 1 — Add `max_length` Parameter to `scan()`

Add a new keyword-only parameter:

```python
def scan(
    data: bytes | memoryview,
    *,
    min_length: int = 4,
    encoding: Literal["s", "S", "l", "b"] = "s",
    include_whitespace: bool = False,
    max_length: int | None = 1022,
) -> Iterator[tuple[int, str]]:
```

- Type is `int | None`. `None` means no limit. Default `1022` matches macOS.
- Pass `max_length` through to both `_scan_ascii()` and `_scan_utf16()`.

If you haven't already split out a `_scan_ascii()` helper, now is a good time.
The `scan()` function should dispatch to `_scan_ascii()` for `"s"` and `"S"`
encodings, and `_scan_utf16()` for `"l"` and `"b"`. Both helpers receive all
the parameters including `max_length`.

### Step 2 — Modify `_scan_ascii()`

Add `max_length: int | None` to the parameter list. Inside the `if printable:`
branch, after `acc.append(data[offset])`, add a forced-flush check:

```python
if max_length is not None and len(acc) >= max_length:
    yield acc_start, acc.decode(codec)
    acc.clear()
```

After the forced flush, `acc` is empty. The loop naturally continues to the
next byte. If that byte is printable, `acc_start` is set to its offset (via the
existing `if not acc: acc_start = offset` logic), starting a new string. If
not, the normal non-printable flush path handles it.

### Step 3 — Modify `_scan_utf16()` Identically

Same pattern, but with `acc_chars` (a `list[str]`) instead of `bytearray`.
`max_length` applies to character count (not byte count), so:

```python
if max_length is not None and len(acc_chars) >= max_length:
    yield acc_start, "".join(acc_chars)
    acc_chars.clear()
```

### Step 4 — CLI Flags in `build_parser()`

Add two flags that share a single `dest`:

```python
parser.add_argument(
    "--max-length", dest="max_length", type=int, default=1022, metavar="NUM",
    help="maximum string length before forced break (default: 1022)",
)
parser.add_argument(
    "--no-max-length", dest="max_length", action="store_const", const=None,
    help="disable the maximum string length limit",
)
```

Both write to `dest="max_length"`. The last one specified wins — standard
argparse behavior. Pass `args.max_length` to `scan()`.

### Step 5 — Tests

Add these test cases to `test_scanner.py`:

| Scenario | `max_length` | Input length | Expected results |
|---|---|---|---|
| No limit | `None` | 2000 chars | One result: 2000 |
| Below limit | `1022` | 500 chars | One result: 500 |
| Exact limit | `1022` | 1022 chars | One result: 1022 |
| One over | `1022` | 1023 chars | One result: 1022 (remainder 1 < `min_length`) |
| Two full chunks | `1022` | 2044 chars | Two results: 1022, 1022 |
| Two chunks + remainder | `1022` | 2050 chars | Three results: 1022, 1022, 6 |
| Small limit | `10` | 25 chars | Three results: 10, 10, 5 |
| Break before limit | `1022` | `b"A"*500 + b"\x00" + b"B"*500` | Two results: 500, 500 |
| UTF-16 LE | `1022` | 1025 UTF-16 chars | Byte offsets spaced at 2 bytes per char |
| Remainder below min_length | `1022` | 1025 chars, `min_length=4` | One result: 1022 (remainder 3 dropped) |

For the UTF-16 test, verify that byte offsets are correct — each character is 2
bytes wide, so the second chunk should start at byte offset `1022 * 2 = 2044`.

### Step 6 — Verification

Create a file with a long printable run and compare against macOS `strings`:

```bash
python3 -c "open('/tmp/longrun.bin','wb').write(b'A'*2050)"
diff <(env LC_ALL=C strings - /tmp/longrun.bin) <(uv run sillystrings --scan-all-bytes /tmp/longrun.bin)
```

If the diff is empty, you match. If not, examine the differences — they should
only be in string lengths, and you can adjust `max_length` if needed.

Run the full test suite and commit:

```
uv run ruff check . --fix && uv run ruff format . && uv run ty check
uv run pytest -v
git add . && git commit -m "add max_length support to scan()"
```

---

## Part 4: Mach-O Section-Aware Scanning

macOS `strings` doesn't just scan every byte of a file. When it encounters a
Mach-O object file (the standard binary format on macOS/iOS), it parses the
file's section table and scans only the initialized data sections — skipping the
`(__TEXT,__text)` section, which contains machine code, not human-readable
strings.

This is why `strings /usr/bin/ls` and `strings - /usr/bin/ls` produce different
output on macOS: the first parses Mach-O and skips code sections; the second
(with `-`) scans all bytes blindly.

After this part, sillystrings will have the same behavior:
- **Default:** parse Mach-O, scan all sections except `(__TEXT,__text)`.
- **`-a` / `--scan-all`:** parse Mach-O, scan ALL sections (including `__text`).
- **`--scan-all-bytes`:** ignore file format entirely, scan all bytes.
- **Non-Mach-O files:** scan all bytes (same as `--scan-all-bytes`).

### Architecture

The scanner stays generic — it just receives byte slices. A new module
`macho.py` handles all format parsing and returns byte ranges to scan:

```
cli.py  →  macho.py (new)
        →  scanner.py  →  encodings.py
```

### Step 1 — Create `src/sillystrings/macho.py` with Data Structures

Start with the constants and data class:

```python
import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    segname: str     # e.g. "__TEXT"
    sectname: str    # e.g. "__text"
    offset: int      # file offset to section data
    size: int        # size in bytes


# Mach-O magic numbers
MACHO_MAGIC_32    = 0xFEEDFACE
MACHO_MAGIC_32_LE = 0xCEFAEDFE
MACHO_MAGIC_64    = 0xFEEDFACF
MACHO_MAGIC_64_LE = 0xCFFAEDFE
FAT_MAGIC         = 0xCAFEBABE

# Load command types
LC_SEGMENT        = 0x01
LC_SEGMENT_64     = 0x19
```

### Step 2 — `is_macho(data)` → `bool`

Read the first 4 bytes as a big-endian `uint32` and check against all 5 magic
numbers:

```python
def is_macho(data: bytes | memoryview) -> bool:
    if len(data) < 4:
        return False
    magic = struct.unpack_from(">I", data, 0)[0]
    return magic in (
        MACHO_MAGIC_32, MACHO_MAGIC_32_LE,
        MACHO_MAGIC_64, MACHO_MAGIC_64_LE,
        FAT_MAGIC,
    )
```

Note: reading as big-endian is just for the comparison. The actual magic bytes
`0xCFFAEDFE` (64-bit LE) are `CF FA ED FE` in the file — when read as
big-endian that gives `0xCFFAEDFE`, which matches the constant.

### Step 3 — `_detect_endian_and_bits(data, offset)` → `tuple[str, bool]`

Given an offset into the file (0 for single Mach-O, or the slice offset for fat
binaries), determine the endianness and bitness:

```python
def _detect_endian_and_bits(
    data: bytes | memoryview, offset: int
) -> tuple[str, bool]:
    """Return (endian_char, is_64bit) for the Mach-O at the given offset."""
    magic = struct.unpack_from(">I", data, offset)[0]
    match magic:
        case 0xFEEDFACF: return (">", True)    # 64-bit BE
        case 0xCFFAEDFE: return ("<", True)     # 64-bit LE
        case 0xFEEDFACE: return (">", False)    # 32-bit BE
        case 0xCEFAEDFE: return ("<", False)    # 32-bit LE
        case _:
            raise ValueError(f"not a Mach-O magic: 0x{magic:08X}")
```

### Step 4 — `_parse_sections(data, base_offset)` → `list[Section]`

This is the main parsing function. It reads the Mach-O header, then walks
through the load commands looking for `LC_SEGMENT` / `LC_SEGMENT_64`:

```python
def _parse_sections(
    data: bytes | memoryview, base_offset: int
) -> list[Section]:
    endian, is_64 = _detect_endian_and_bits(data, base_offset)

    # Read header to get ncmds
    if is_64:
        header = struct.unpack_from(f"{endian}8I", data, base_offset)
        cmd_offset = base_offset + 32  # 64-bit header is 32 bytes
    else:
        header = struct.unpack_from(f"{endian}7I", data, base_offset)
        cmd_offset = base_offset + 28  # 32-bit header is 28 bytes

    ncmds = header[4]
    sections: list[Section] = []

    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from(f"{endian}2I", data, cmd_offset)

        if cmd == LC_SEGMENT_64 and is_64:
            sections.extend(
                _parse_segment_sections_64(data, cmd_offset, endian)
            )
        elif cmd == LC_SEGMENT and not is_64:
            sections.extend(
                _parse_segment_sections_32(data, cmd_offset, endian)
            )

        cmd_offset += cmdsize

    return sections
```

The header fields by index:

| Index | 32-bit | 64-bit |
|---|---|---|
| 0 | magic | magic |
| 1 | cputype | cputype |
| 2 | cpusubtype | cpusubtype |
| 3 | filetype | filetype |
| 4 | **ncmds** | **ncmds** |
| 5 | sizeofcmds | sizeofcmds |
| 6 | flags | flags |
| 7 | — | reserved |

### Step 5 — Segment and Section Parsing

These two functions parse the sections within an `LC_SEGMENT_64` or
`LC_SEGMENT` load command.

**64-bit segments:**

```python
def _parse_segment_sections_64(
    data: bytes | memoryview, cmd_offset: int, endian: str
) -> list[Section]:
    # LC_SEGMENT_64 structure: '{e}2I16s4Q4I' = 72 bytes
    seg = struct.unpack_from(f"{endian}2I16s4Q4I", data, cmd_offset)
    nsects = seg[9]

    sections: list[Section] = []
    sect_offset = cmd_offset + 72  # sections start after segment header

    for _ in range(nsects):
        # section_64 structure: '{e}16s16s2Q8I' = 80 bytes
        s = struct.unpack_from(f"{endian}16s16s2Q8I", data, sect_offset)
        sectname = s[0].rstrip(b"\x00").decode("ascii", errors="replace")
        segname = s[1].rstrip(b"\x00").decode("ascii", errors="replace")
        size = s[3]
        offset = s[4]
        sections.append(Section(segname=segname, sectname=sectname,
                                offset=offset, size=size))
        sect_offset += 80

    return sections
```

**32-bit segments:**

```python
def _parse_segment_sections_32(
    data: bytes | memoryview, cmd_offset: int, endian: str
) -> list[Section]:
    # LC_SEGMENT structure: '{e}2I16s8I' = 56 bytes
    seg = struct.unpack_from(f"{endian}2I16s8I", data, cmd_offset)
    nsects = seg[9]

    sections: list[Section] = []
    sect_offset = cmd_offset + 56  # sections start after segment header

    for _ in range(nsects):
        # section (32-bit) structure: '{e}16s16s9I' = 68 bytes
        s = struct.unpack_from(f"{endian}16s16s9I", data, sect_offset)
        sectname = s[0].rstrip(b"\x00").decode("ascii", errors="replace")
        segname = s[1].rstrip(b"\x00").decode("ascii", errors="replace")
        size = s[3]
        offset = s[4]
        sections.append(Section(segname=segname, sectname=sectname,
                                offset=offset, size=size))
        sect_offset += 68

    return sections
```

**Struct format string reference table:**

| Structure | Format | Size (bytes) | Key fields (by index) |
|---|---|---|---|
| Mach-O header 64 | `'{e}8I'` | 32 | ncmds=4, sizeofcmds=5 |
| Mach-O header 32 | `'{e}7I'` | 28 | ncmds=4, sizeofcmds=5 |
| Load cmd header | `'{e}2I'` | 8 | cmd=0, cmdsize=1 |
| LC_SEGMENT_64 | `'{e}2I16s4Q4I'` | 72 | segname=2, nsects=9 |
| LC_SEGMENT | `'{e}2I16s8I'` | 56 | segname=2, nsects=9 |
| section_64 | `'{e}16s16s2Q8I'` | 80 | sectname=0, segname=1, size=3, offset=4 |
| section (32) | `'{e}16s16s9I'` | 68 | sectname=0, segname=1, size=3, offset=4 |
| Fat header | `'>2I'` | 8 | magic=0, nfat_arch=1 (always BE) |
| Fat arch | `'>5I'` | 20 | offset=2, size=3 (always BE) |

Where `{e}` is `<` or `>` based on magic number.

### Step 6 — `_parse_fat_binary(data)` → `list[tuple[int, list[Section]]]`

Fat (universal) binaries contain multiple Mach-O slices (one per architecture).
The fat header is always big-endian, regardless of the endianness of the
contained slices:

```python
def _parse_fat_binary(
    data: bytes | memoryview,
) -> list[tuple[int, list[Section]]]:
    # Fat header: '>2I' = (magic, nfat_arch), always big-endian
    _, nfat_arch = struct.unpack_from(">2I", data, 0)

    results: list[tuple[int, list[Section]]] = []
    arch_offset = 8  # fat_arch entries start after the 8-byte header

    for _ in range(nfat_arch):
        # fat_arch: '>5I' = (cputype, cpusubtype, offset, size, align)
        arch = struct.unpack_from(">5I", data, arch_offset)
        slice_offset = arch[2]
        sections = _parse_sections(data, slice_offset)
        results.append((slice_offset, sections))
        arch_offset += 20

    return results
```

### Step 7 — Public API: `get_scan_ranges()`

This is what `cli.py` calls. It returns a list of `(offset, size)` tuples
representing the byte ranges to scan:

```python
def get_scan_ranges(
    data: bytes | memoryview, *, include_all: bool = False
) -> list[tuple[int, int]]:
    if not is_macho(data):
        return [(0, len(data))]

    try:
        magic = struct.unpack_from(">I", data, 0)[0]

        if magic == FAT_MAGIC:
            all_sections: list[Section] = []
            for _, sections in _parse_fat_binary(data):
                all_sections.extend(sections)
        else:
            all_sections = _parse_sections(data, 0)

        ranges: list[tuple[int, int]] = []
        for section in all_sections:
            if section.size == 0:
                continue
            if (not include_all
                    and section.segname == "__TEXT"
                    and section.sectname == "__text"):
                continue
            ranges.append((section.offset, section.size))

        return ranges if ranges else [(0, len(data))]

    except struct.error:
        # Corrupt or truncated Mach-O — fall back to whole-file scan
        return [(0, len(data))]
```

Key behaviors:
- Non-Mach-O files: returns `[(0, len(data))]` — scan everything.
- By default, skips only the exact section `(__TEXT,__text)` — not
  `(__TEXT,__textcoal_nt)`, not `(__DATA,__text)`.
- With `include_all=True`, includes everything.
- Skips zero-size sections.
- Wraps parsing in `try/except struct.error` — corrupt Mach-O falls back to
  whole-file scan rather than crashing.

### Step 8 — CLI Changes

Update `build_parser()` in `cli.py`. Replace the existing `-a` / `--all` flag
with proper Mach-O-aware flags:

```python
parser.add_argument(
    "-a", "--scan-all", action="store_true", default=False,
    help="scan all sections of Mach-O files (including __text)",
)
parser.add_argument(
    "--scan-all-bytes", action="store_true", default=False,
    help="scan all bytes regardless of file format",
)
```

Remove the old `-a` / `--all` compatibility flag — it's being replaced with
real functionality.

### Step 9 — Modify `main()` to Use Section-Aware Scanning

```python
from sillystrings.macho import get_scan_ranges, is_macho

# Inside main(), for each source:
if args.scan_all_bytes or not is_macho(source.data):
    ranges = [(0, len(source.data))]
else:
    ranges = get_scan_ranges(source.data, include_all=args.scan_all)

for range_offset, range_size in ranges:
    section_data = memoryview(source.data)[range_offset:range_offset + range_size]
    for offset, string in scan(section_data, ...):
        true_offset = range_offset + offset  # adjust to file-level offset
        print(string)  # or with offset formatting using true_offset
```

**Critical detail:** `scan()` returns offsets relative to the slice it receives.
You must add `range_offset` to get the true file-level offset. Use `memoryview`
for the slice to avoid copying data.

### Step 10 — Tests

Create `tests/test_macho.py`. Include a helper function that builds a minimal
synthetic 64-bit LE Mach-O for unit testing — this avoids depending on external
binaries:

```python
def build_macho_64_le(
    sections: list[tuple[str, str, int, int]],
) -> bytearray:
    """Build a minimal 64-bit LE Mach-O from (segname, sectname, offset, size) tuples.

    Groups sections by segment name automatically.
    """
    ...
```

The helper should:
1. Group sections by `segname`.
2. Build one `LC_SEGMENT_64` load command per unique segment.
3. Append section headers within each segment command.
4. Build the Mach-O header with `magic=0xCFFAEDFE`, `ncmds`, and `sizeofcmds`.
5. Return a `bytearray` of the complete file.

**Test cases:**

| Test | What it checks |
|---|---|
| `is_macho` — all 5 magics | Detects 32/64 BE/LE and fat magic |
| `is_macho` — non-Mach-O | Returns `False` for random bytes, empty data, short data |
| `_parse_sections` | Correct names, offsets, and sizes from synthetic Mach-O |
| `get_scan_ranges` — default | Excludes `(__TEXT,__text)`, includes all other sections |
| `get_scan_ranges` — `include_all` | Includes everything including `(__TEXT,__text)` |
| `get_scan_ranges` — non-Mach-O | Returns `[(0, len)]` |
| Exact name match | `(__TEXT,__textcoal_nt)` is NOT excluded (only exact `__text`) |
| Exact segment match | `(__DATA,__text)` is NOT excluded (segment must be `__TEXT`) |
| Fat binary | Parses slice offsets and collects sections from all architectures |
| Corrupt/truncated Mach-O | Falls back to `[(0, len)]` without crashing |
| Smoke test | Against `fixtures/tool.bin` if available (skip if not) |

### Step 11 — Verification Against Real macOS `strings`

```bash
diff <(env LC_ALL=C strings fixtures/tool.bin) \
     <(uv run sillystrings fixtures/tool.bin)

diff <(env LC_ALL=C strings -a fixtures/tool.bin) \
     <(uv run sillystrings -a fixtures/tool.bin)

diff <(env LC_ALL=C strings - fixtures/tool.bin) \
     <(uv run sillystrings --scan-all-bytes fixtures/tool.bin)
```

> **Note:** `LC_ALL=C` is needed because macOS `strings` uses the
> locale-dependent `isprint()` function. In UTF-8 locales, it considers high
> bytes (0x80–0xFF) printable. The C locale restricts to 0x20–0x7E, matching
> sillystrings' `-e s` behavior.

Run the full test suite and commit:

```
uv run ruff check . --fix && uv run ruff format . && uv run ty check
uv run pytest -v
git add . && git commit -m "add Mach-O section-aware scanning"
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
from typing import Literal

from sillystrings.encodings import iter_chars


def scan(
    data: bytes | memoryview,
    *,
    min_length: int = 4,
    encoding: Literal["s", "S", "l", "b"] = "s",
    include_whitespace: bool = False,
    max_length: int | None = 1022,
) -> Iterator[tuple[int, str]]:
    """Yield (byte_offset, string) for each printable run in data."""
    if encoding in ("l", "b"):
        yield from _scan_utf16(
            data,
            min_length=min_length,
            encoding=encoding,
            include_whitespace=include_whitespace,
            max_length=max_length,
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
            if max_length is not None and len(acc) >= max_length:
                yield acc_start, acc.decode(codec)
                acc.clear()
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
    max_length: int | None,
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
            if max_length is not None and len(acc_chars) >= max_length:
                yield acc_start, "".join(acc_chars)
                acc_chars.clear()
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

from sillystrings.macho import get_scan_ranges, is_macho
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
        "-a", "--scan-all", action="store_true", default=False,
        help="scan all sections of Mach-O files (including __text)",
    )
    p.add_argument(
        "--scan-all-bytes", action="store_true", default=False,
        help="scan all bytes regardless of file format",
    )
    p.add_argument("-f", "--print-file-name", action="store_true")
    p.add_argument(
        "--max-length", dest="max_length", type=int, default=1022, metavar="NUM",
        help="maximum string length before forced break (default: 1022)",
    )
    p.add_argument(
        "--no-max-length", dest="max_length", action="store_const", const=None,
        help="disable the maximum string length limit",
    )
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
        if args.scan_all_bytes or not is_macho(data):
            ranges = [(0, len(data))]
        else:
            ranges = get_scan_ranges(data, include_all=args.scan_all)

        for range_offset, range_size in ranges:
            section_data = memoryview(data)[range_offset:range_offset + range_size]
            for offset, string in scan(
                section_data,
                min_length=args.min_length,
                encoding=args.encoding,
                include_whitespace=args.include_all_whitespace,
                max_length=args.max_length,
            ):
                true_offset = range_offset + offset
                prefix = f"{name}: " if (multiple or args.print_file_name) else ""
                print(f"{prefix}{format_offset(true_offset, args.radix)}{string}")
```

> **Note:** `argparse.FileType("rb")` opens files during `parse_args()`, so
> error messages for missing files come from argparse rather than your own code.
> That's a reasonable tradeoff for a project of this size.
>
> **Note:** `scan()` returns offsets relative to the slice it receives. The
> `range_offset + offset` calculation converts to file-level offsets. Using
> `memoryview` for slicing avoids copying data.

---

## `macho.py` — Full Implementation

```python
# src/sillystrings/macho.py
"""Mach-O binary format parser for section-aware string scanning."""

import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    segname: str
    sectname: str
    offset: int
    size: int


MACHO_MAGIC_32 = 0xFEEDFACE
MACHO_MAGIC_32_LE = 0xCEFAEDFE
MACHO_MAGIC_64 = 0xFEEDFACF
MACHO_MAGIC_64_LE = 0xCFFAEDFE
FAT_MAGIC = 0xCAFEBABE
LC_SEGMENT = 0x01
LC_SEGMENT_64 = 0x19


def is_macho(data: bytes | memoryview) -> bool:
    """Return True if data begins with a Mach-O or fat binary magic number."""
    if len(data) < 4:
        return False
    magic = struct.unpack_from(">I", data, 0)[0]
    return magic in (
        MACHO_MAGIC_32,
        MACHO_MAGIC_32_LE,
        MACHO_MAGIC_64,
        MACHO_MAGIC_64_LE,
        FAT_MAGIC,
    )


def _detect_endian_and_bits(
    data: bytes | memoryview, offset: int
) -> tuple[str, bool]:
    """Return (endian_char, is_64bit) for the Mach-O at the given offset."""
    magic = struct.unpack_from(">I", data, offset)[0]
    match magic:
        case 0xFEEDFACF:
            return (">", True)
        case 0xCFFAEDFE:
            return ("<", True)
        case 0xFEEDFACE:
            return (">", False)
        case 0xCEFAEDFE:
            return ("<", False)
        case _:
            raise ValueError(f"not a Mach-O magic: 0x{magic:08X}")


def _parse_segment_sections_64(
    data: bytes | memoryview, cmd_offset: int, endian: str
) -> list[Section]:
    seg = struct.unpack_from(f"{endian}2I16s4Q4I", data, cmd_offset)
    nsects = seg[9]

    sections: list[Section] = []
    sect_offset = cmd_offset + 72

    for _ in range(nsects):
        s = struct.unpack_from(f"{endian}16s16s2Q8I", data, sect_offset)
        sectname = s[0].rstrip(b"\x00").decode("ascii", errors="replace")
        segname = s[1].rstrip(b"\x00").decode("ascii", errors="replace")
        size = s[3]
        offset = s[4]
        sections.append(
            Section(segname=segname, sectname=sectname, offset=offset, size=size)
        )
        sect_offset += 80

    return sections


def _parse_segment_sections_32(
    data: bytes | memoryview, cmd_offset: int, endian: str
) -> list[Section]:
    seg = struct.unpack_from(f"{endian}2I16s8I", data, cmd_offset)
    nsects = seg[9]

    sections: list[Section] = []
    sect_offset = cmd_offset + 56

    for _ in range(nsects):
        s = struct.unpack_from(f"{endian}16s16s9I", data, sect_offset)
        sectname = s[0].rstrip(b"\x00").decode("ascii", errors="replace")
        segname = s[1].rstrip(b"\x00").decode("ascii", errors="replace")
        size = s[3]
        offset = s[4]
        sections.append(
            Section(segname=segname, sectname=sectname, offset=offset, size=size)
        )
        sect_offset += 68

    return sections


def _parse_sections(
    data: bytes | memoryview, base_offset: int
) -> list[Section]:
    """Parse all sections from a single Mach-O at base_offset."""
    endian, is_64 = _detect_endian_and_bits(data, base_offset)

    if is_64:
        header = struct.unpack_from(f"{endian}8I", data, base_offset)
        cmd_offset = base_offset + 32
    else:
        header = struct.unpack_from(f"{endian}7I", data, base_offset)
        cmd_offset = base_offset + 28

    ncmds = header[4]
    sections: list[Section] = []

    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from(f"{endian}2I", data, cmd_offset)

        if cmd == LC_SEGMENT_64 and is_64:
            sections.extend(
                _parse_segment_sections_64(data, cmd_offset, endian)
            )
        elif cmd == LC_SEGMENT and not is_64:
            sections.extend(
                _parse_segment_sections_32(data, cmd_offset, endian)
            )

        cmd_offset += cmdsize

    return sections


def _parse_fat_binary(
    data: bytes | memoryview,
) -> list[tuple[int, list[Section]]]:
    """Parse a fat (universal) binary and return sections for each slice."""
    _, nfat_arch = struct.unpack_from(">2I", data, 0)

    results: list[tuple[int, list[Section]]] = []
    arch_offset = 8

    for _ in range(nfat_arch):
        arch = struct.unpack_from(">5I", data, arch_offset)
        slice_offset = arch[2]
        sections = _parse_sections(data, slice_offset)
        results.append((slice_offset, sections))
        arch_offset += 20

    return results


def get_scan_ranges(
    data: bytes | memoryview, *, include_all: bool = False
) -> list[tuple[int, int]]:
    """Return (offset, size) pairs for the byte ranges to scan.

    By default, excludes the (__TEXT,__text) section from Mach-O files.
    Pass include_all=True to include all sections.
    Returns [(0, len(data))] for non-Mach-O files or on parse failure.
    """
    if not is_macho(data):
        return [(0, len(data))]

    try:
        magic = struct.unpack_from(">I", data, 0)[0]

        if magic == FAT_MAGIC:
            all_sections: list[Section] = []
            for _, sections in _parse_fat_binary(data):
                all_sections.extend(sections)
        else:
            all_sections = _parse_sections(data, 0)

        ranges: list[tuple[int, int]] = []
        for section in all_sections:
            if section.size == 0:
                continue
            if (
                not include_all
                and section.segname == "__TEXT"
                and section.sectname == "__text"
            ):
                continue
            ranges.append((section.offset, section.size))

        return ranges if ranges else [(0, len(data))]

    except struct.error:
        return [(0, len(data))]
```

### `build_macho_64_le()` — Test Helper

Use this in `tests/test_macho.py` to build synthetic Mach-O files without
depending on external binaries:

```python
def build_macho_64_le(
    sections: list[tuple[str, str, int, int]],
) -> bytearray:
    """Build a minimal 64-bit LE Mach-O from (segname, sectname, offset, size) tuples."""
    endian = "<"

    # Group sections by segment name (preserving order)
    segments: dict[str, list[tuple[str, str, int, int]]] = {}
    for segname, sectname, offset, size in sections:
        segments.setdefault(segname, []).append((segname, sectname, offset, size))

    # Build load commands
    load_commands = bytearray()
    for segname, seg_sections in segments.items():
        nsects = len(seg_sections)
        # LC_SEGMENT_64 header: 72 bytes + 80 bytes per section
        cmdsize = 72 + nsects * 80

        # Segment header: cmd, cmdsize, segname[16], vmaddr, vmsize,
        #                  fileoff, filesize, maxprot, initprot, nsects, flags
        seg_name_bytes = segname.encode("ascii").ljust(16, b"\x00")[:16]
        seg_header = struct.pack(
            f"{endian}2I16s4Q4I",
            LC_SEGMENT_64,  # cmd
            cmdsize,        # cmdsize
            seg_name_bytes, # segname
            0, 0, 0, 0,    # vmaddr, vmsize, fileoff, filesize
            0, 0,           # maxprot, initprot
            nsects,         # nsects
            0,              # flags
        )
        load_commands.extend(seg_header)

        # Section headers
        for s_segname, s_sectname, s_offset, s_size in seg_sections:
            sect_name_bytes = s_sectname.encode("ascii").ljust(16, b"\x00")[:16]
            s_seg_name_bytes = s_segname.encode("ascii").ljust(16, b"\x00")[:16]
            sect_header = struct.pack(
                f"{endian}16s16s2Q8I",
                sect_name_bytes,    # sectname
                s_seg_name_bytes,   # segname
                0,                  # addr
                s_size,             # size
                s_offset,           # offset
                0,                  # align
                0, 0,               # reloff, nreloc
                0, 0, 0, 0,        # flags, reserved1, reserved2, reserved3
            )
            load_commands.extend(sect_header)

    # Mach-O header (64-bit): magic, cputype, cpusubtype, filetype,
    #                          ncmds, sizeofcmds, flags, reserved
    ncmds = len(segments)
    header = struct.pack(
        f"{endian}8I",
        0xCFFAEDFE,             # magic (64-bit LE)
        0x01000007,             # cputype (x86_64)
        0x00000003,             # cpusubtype
        0x00000002,             # filetype (MH_EXECUTE)
        ncmds,                  # ncmds
        len(load_commands),     # sizeofcmds
        0,                      # flags
        0,                      # reserved
    )

    return bytearray(header) + load_commands
```

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
