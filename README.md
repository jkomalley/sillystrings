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
| `-e {s,S,l,b}` | Character encoding: `s` = 7-bit ASCII (default), `S` = 8-bit, `l` = UTF-16 LE, `b` = UTF-16 BE |
| `-t {d,o,x}` | Print byte offset before each string in decimal, octal, or hex |
| `-w` | Include all whitespace characters (newlines, carriage returns) in strings |
| `-f` | Print the filename before each string |
| `-v` | Show version and exit |

### Examples

Scan a binary for readable strings:

```
sillystrings /usr/bin/ls
```

Show hex offsets with 8-bit encoding:

```
sillystrings -t x -e S firmware.bin
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

The project is organized into three layers:

- **encodings** -- character-level printability checks for ASCII and UTF-16
- **scanner** -- accumulates printable runs into strings, tracks byte offsets
- **cli** -- argument parsing, file I/O, output formatting

## Development

```
uv sync
uv run pytest
```

Tests cover all encoding modes, offset calculations, CLI flags, edge cases, and integration via subprocess.

## License

MIT
