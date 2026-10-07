#!/usr/bin/env python3
"""Compare sillystrings with GNU strings, for -d and -a, on any files.

Usage: uv run scripts/compare_gnu.py [--gnu PATH] [-n MIN] [-e ENC ...] FILE [FILE ...]
Requires: a GNU strings that understands your files' formats. On macOS,
`brew install binutils` provides one that reads Mach-O and ELF; it is keg-only, so it
does not shadow the system strings. That is the default for --gnu.

For each file, mode and encoding, runs `sillystrings MODE -e ENC -n MIN -t d FILE`
and the same with GNU strings, and prints a table of whether the outputs are
byte-identical. Repeat -e to compare several encodings; the default is s.
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
    parser.add_argument(
        "-e",
        dest="encodings",
        action="append",
        choices=["s", "S", "l", "b", "L", "B"],
        help="an encoding to compare (repeatable; default s)",
    )
    args = parser.parse_args()
    encodings = args.encodings or ["s"]
    gnu_strings = args.gnu or default_gnu()
    ours_cmd = [sys.executable, "-m", "sillystrings.cli"]

    print(f"GNU: {run([gnu_strings, '--version']).decode().splitlines()[0]}\n")
    print("| file | mode | encoding | lines | result |")
    print("|---|---|---|---|---|")
    failed = False
    differences = []
    for path in args.files:
        for mode in MODES:
            for encoding in encodings:
                common = [mode, "-e", encoding, "-n", str(args.min_length)]
                common += ["-t", "d", str(path)]
                ours = parse(run([*ours_cmd, *common]))
                gnu = parse(run([gnu_strings, *common]))
                if ours == gnu:
                    result = "match"
                else:
                    result = "**DIFF**"
                    failed = True
                    where = first_difference(ours, gnu)
                    differences.append(f"{path} {mode} -e {encoding}: {where}")
                cells = [path.name, f"`{mode}`", f"`{encoding}`", len(ours), result]
                print("| " + " | ".join(map(str, cells)) + " |")
    for line in differences:
        print(f"\n{line}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
