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

FIXTURES = Path(__file__).parent.parent / "fixtures"
BINARY = FIXTURES / "tool.bin"
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
