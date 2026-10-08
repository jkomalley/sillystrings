#!/usr/bin/env python3
"""Compare sillystrings with GNU strings on any files, in any modes and flags.

Usage: uv run scripts/compare_gnu.py [--gnu PATH] [-n MIN] [-e ENC ...]
           [-m {d,a} ...] [-x=FLAGS ...] FILE [FILE ...]
Requires: a GNU strings that understands your files' formats. On macOS,
`brew install binutils` provides one that reads Mach-O and ELF; it is keg-only, so it
does not shadow the system strings. That is the default for --gnu.

For each file, mode, encoding and flag set, runs
`sillystrings MODE -e ENC -n MIN FLAGS FILE` and the same with GNU strings, and
prints a table of whether the outputs are byte-identical. Each option repeats:
-e defaults to s, -m to both d and a, and -x, a set of extra flags split like a
shell would, to "-t d". Pass -x as -x="-w -t x" or -x=-f, with "=", or argparse
reads a flag set that starts with a dash as an option of its own.
"""

import argparse
import contextlib
import io
import shlex
import subprocess
import sys
from pathlib import Path
from unittest import mock

from sillystrings import cli


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


def run_ours(args: list[str]) -> bytes:
    """Run sillystrings in this process and return what it wrote to stdout.

    Starting a fresh interpreter per run cost about 60ms, which dominated a
    comparison of many small files; the installed entry point is covered by the
    test suite's subprocess tests instead.
    """
    stdout = io.TextIOWrapper(io.BytesIO())
    with (
        mock.patch.object(sys, "argv", ["sillystrings", *args]),
        contextlib.redirect_stdout(stdout),
    ):
        cli.main()
    return stdout.buffer.getvalue()


def first_difference(ours: bytes, gnu: bytes) -> str:
    """Describe the first output line where two outputs differ.

    Outputs are compared whole, since with -w a string can itself contain a
    newline; splitting on newlines is only to point at roughly where they part.
    """
    ours_lines, gnu_lines = ours.split(b"\n"), gnu.split(b"\n")
    for index, (a, b) in enumerate(zip(ours_lines, gnu_lines, strict=False)):
        if a != b:
            return f"line {index + 1}: ours {a!r}, GNU {b!r}"
    return f"ours has {len(ours_lines)} lines, GNU has {len(gnu_lines)}"


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
    parser.add_argument(
        "-m",
        dest="modes",
        action="append",
        choices=["d", "a"],
        help="a mode to compare, -d or -a, without its dash (repeatable; default both)",
    )
    parser.add_argument(
        "-x",
        dest="flag_sets",
        action="append",
        metavar="FLAGS",
        help='a set of extra flags, such as -x="-w -t x"; write it with "=" so it'
        ' is not read as an option (repeatable; default "-t d")',
    )
    args = parser.parse_args()
    encodings = args.encodings or ["s"]
    modes = [f"-{mode}" for mode in args.modes or ["d", "a"]]
    flag_sets = args.flag_sets or ["-t d"]
    gnu_strings = args.gnu or default_gnu()

    print(f"GNU: {run([gnu_strings, '--version']).decode().splitlines()[0]}\n")
    print("| file | mode | encoding | flags | lines | result |")
    print("|---|---|---|---|---|---|")
    failed = False
    differences = []
    for path in args.files:
        for mode in modes:
            for encoding in encodings:
                for flags in flag_sets:
                    common = [mode, "-e", encoding, "-n", str(args.min_length)]
                    common += [*shlex.split(flags), str(path)]
                    ours = run_ours(common)
                    gnu = run([gnu_strings, *common])
                    if ours == gnu:
                        result = "match"
                    else:
                        result = "**DIFF**"
                        failed = True
                        where = first_difference(ours, gnu)
                        differences.append(
                            f"{path} {mode} -e {encoding} {flags}: {where}"
                        )
                    cells = [
                        path.name,
                        f"`{mode}`",
                        f"`{encoding}`",
                        f"`{flags}`",
                        ours.count(b"\n"),
                        result,
                    ]
                    print("| " + " | ".join(map(str, cells)) + " |")
    for line in differences:
        print(f"\n{line}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
