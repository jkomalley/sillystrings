#!/usr/bin/env python3
"""Write seeded random files that stress string boundaries, for compare_gnu.py.

Usage: uv run scripts/random_corpus.py OUTDIR [--count N] [--seed S]

Each file is drawn from a small alphabet of printable, whitespace, NUL and high
bytes, so short strings, tabs, newlines and partly printable wide characters
occur at every alignment far more often than in real binaries. The same seed
always writes the same files, so a difference CI finds can be reproduced locally.
"""

import argparse
import random
from pathlib import Path

ALPHABET = b"aZ7 \t\n\r\x0b\x0c\x00\x00\x00\x01\x7f\x80\xe9\xff"


def main() -> None:
    """Write --count files of varying length into OUTDIR."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("outdir", type=Path)
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    rng = random.Random(args.seed)  # noqa: S311 -- reproducible, not secret
    args.outdir.mkdir(parents=True, exist_ok=True)
    for index in range(args.count):
        size = rng.choice([0, 1, 2, 3, 5, 8, 64, 1024, 65536])
        data = bytes(rng.choice(ALPHABET) for _ in range(size))
        (args.outdir / f"random-{index:03}.bin").write_bytes(data)


if __name__ == "__main__":
    main()
