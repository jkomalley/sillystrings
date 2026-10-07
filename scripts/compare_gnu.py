#!/usr/bin/env python3
"""Compare sillystrings with GNU strings, for -d and -a, on any files.

Usage: uv run scripts/compare_gnu.py [--gnu PATH] [-n MIN] FILE [FILE ...]
Requires: a GNU strings that understands your files' formats. On macOS,
`brew install binutils` provides one that reads Mach-O; it is keg-only, so it
does not shadow the system strings. That is the default for --gnu.

For each file and mode, runs `sillystrings MODE -n MIN -t d FILE` and the same
with GNU strings, and prints a table of whether they match.

GNU strings counts tab as printable by default; sillystrings does not (only with
-w), which is a known, separate difference. Without accounting for it, any
string with a tab in it would show as a mismatch and hide the differences this
script is for. So GNU's output is normalized first: each string is split on
tabs, each piece is given the string's offset plus the piece's index within it,
and only pieces of at least MIN characters are kept. Those are exactly the runs
sillystrings finds, because tab is the only character the two tools disagree
on. The raw comparison is printed too, so the size of the tab effect is visible.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

MODES = ["-d", "-a"]
LINE = re.compile(rb" *(\d+) (.*)", re.DOTALL)


def default_gnu() -> str:
    """Return Homebrew binutils' strings, or "strings" if Homebrew is absent."""
    try:
        prefix = subprocess.run(
            ["brew", "--prefix", "binutils"],  # noqa: S607 -- found on PATH
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "strings"
    return str(Path(prefix, "bin", "strings"))


def run(argv: list[str]) -> bytes:
    """Run a command and return its stdout, which is all either tool prints."""
    return subprocess.run(argv, capture_output=True, check=True).stdout


def parse(output: bytes) -> list[tuple[int, bytes]]:
    """Split `-t d` output into (offset, string) pairs."""
    pairs = []
    for line in output.split(b"\n")[:-1]:
        match = LINE.fullmatch(line)
        if match is None:
            sys.exit(f"unexpected output line: {line!r}")
        pairs.append((int(match[1]), match[2]))
    return pairs


def split_tabs(pairs: list[tuple[int, bytes]], min_length: int) -> list:
    """Turn GNU's strings into the runs sillystrings finds, which stop at tabs."""
    result = []
    for offset, string in pairs:
        index = 0
        for piece in string.split(b"\t"):
            if len(piece) >= min_length:
                result.append((offset + index, piece))
            index += len(piece) + 1
    return result


def first_difference(ours: list, gnu: list) -> str:
    """Describe where two lists of (offset, string) first differ."""
    for index, (a, b) in enumerate(zip(ours, gnu, strict=False)):
        if a != b:
            return f"line {index + 1}: ours {a!r}, GNU {b!r}"
    return f"ours has {len(ours)} lines, GNU has {len(gnu)}"


def main() -> None:
    """Compare both tools on each file and print a Markdown table."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", metavar="FILE", nargs="+", type=Path)
    parser.add_argument("--gnu", default=None, help="the GNU strings to run")
    parser.add_argument("-n", dest="min_length", type=int, default=4)
    args = parser.parse_args()
    gnu_strings = args.gnu or default_gnu()
    ours_cmd = [sys.executable, "-m", "sillystrings.cli"]

    print(f"GNU: {run([gnu_strings, '--version']).decode().splitlines()[0]}\n")
    print("| file | mode | lines | raw | tab-normalized |")
    print("|---|---|---|---|---|")
    failed = False
    differences = []
    for path in args.files:
        for mode in MODES:
            common = [mode, "-n", str(args.min_length), "-t", "d", str(path)]
            ours_raw = run([*ours_cmd, *common])
            gnu_raw = run([gnu_strings, *common])
            ours = parse(ours_raw)
            gnu = split_tabs(parse(gnu_raw), args.min_length)
            raw = "identical" if ours_raw == gnu_raw else "differs"
            if ours == gnu:
                normalized = "match"
            else:
                normalized = "**DIFF**"
                failed = True
                differences.append(f"{path} {mode}: {first_difference(ours, gnu)}")
            print(f"| {path.name} | `{mode}` | {len(ours)} | {raw} | {normalized} |")
    for line in differences:
        print(f"\n{line}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
