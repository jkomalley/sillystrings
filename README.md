# sillystrings

A Python reimplementation of the Unix `strings` utility. Extracts printable character sequences from binary files with support for multiple encodings, offset display, and standard CLI conventions.

Pure Python, zero dependencies, comprehensive test coverage.

## Installation

Requires Python 3.11+.

Install from source using [uv](https://docs.astral.sh/uv/):

```
git clone https://github.com/jkomalley/sillystrings.git
cd sillystrings
uv sync
```

## Usage

```
sillystrings [OPTIONS] [FILE ...]
```

With no file arguments, reads from stdin.

### Options

| Flag | Description |
|------|-------------|
| `-n NUM` | Minimum string length (default: 4) |
| `-e {s,S,l,b,L,B}` | Character encoding: `s` = 7-bit ASCII (default), `S` = 8-bit, `l` = UTF-16 LE, `b` = UTF-16 BE, `L` = 32-bit LE, `B` = 32-bit BE |
| `-t {d,o,x}` | Print byte offset before each string in decimal, octal, or hex |
| `-o` | Same as `-t o` |
| `-a`, `--all` | Scan the whole file (the default) |
| `-d`, `--data` | Scan only the data sections of an object file; see below |
| `-w` | Include all whitespace characters (newlines, carriage returns) in strings |
| `-f` | Print the filename before each string |
| `-v` | Show version and exit |

### Scanning only data sections

By default every byte of a file is scanned. With `-d`, `sillystrings` follows GNU
`strings -d`: when the file is an object it recognizes, only the sections
loaded into memory from the file are scanned, and each section is scanned on its
own, so a string never runs across a section boundary. Offsets are still from
the start of the file.

| Mode | Recognized object | Anything else |
|------|-------------------|---------------|
| default, `-a` | Whole file | Whole file |
| `-d` | Data sections | Whole file |

`-a` and `-d` override each other, so the last one given wins. Thin Mach-O
files (32- and 64-bit, either byte order) are recognized so far; ELF is
[planned](https://github.com/jkomalley/sillystrings/issues/3). For
well-formed objects, the output matches GNU `strings -d`:

- "Data" means every section loaded with content from the file, **code
  included**. Zero-filled sections (such as `__bss`) and debug sections are
  skipped.
- Fat (universal) Mach-O files and static archives (`.a`) are scanned whole.
- A recognized object with no data sections is scanned whole.
- `-d` does not apply to stdin, which is always scanned whole.
- A section whose bytes lie outside the file is skipped, and the rest are
  scanned.

Malformed input may differ from GNU, which rejects some damaged objects we
accept and accepts some we reject. Either way `sillystrings` never crashes: a
damaged header or load commands mean the file is not treated as an object, and
it is scanned whole. Separately, unlike GNU, where `-` is another spelling of
`-a`, a `-` argument here means stdin.

This is GNU's behavior, not macOS `strings`'. Apple's `strings` parses Mach-O
by default, skips only `(__TEXT,__text)`, reads just one slice of a fat file,
and uses `-a` to mean all sections, so its output differs from both modes here.

### Examples

Scan a binary for readable strings:

```
sillystrings /usr/bin/ls
```

Show hex offsets with 8-bit encoding:

```
sillystrings -t x -e S firmware.bin
```

Scan only the data sections of a Mach-O object:

```
sillystrings -d build/main.o
```

Read from stdin:

```
cat firmware.bin | sillystrings -
```

Find wide (UTF-16 LE) strings with a minimum length of 8:

```
sillystrings -e l -n 8 program.exe
```

## Architecture

The project is organized into four layers:

- **encodings** -- character-level printability checks for ASCII and 16- and 32-bit wide characters
- **scanner** -- accumulates printable runs into strings, tracks byte offsets
- **formats** -- parses object file formats to find the data sections `-d` scans
- **cli** -- argument parsing, file I/O, output formatting

## Development

```
just install    # or: uv sync && uv run pre-commit install
just check      # format, lint, type check, and the test suite
```

Tests cover all encoding modes, offset calculations, CLI flags, edge cases, and integration via subprocess.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, project layout, and the conventions this repo follows.

## License

MIT
