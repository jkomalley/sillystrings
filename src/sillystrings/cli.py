# src/sillystrings/cli.py
import argparse
from dataclasses import dataclass

from sillystrings.__version__ import __version__
from sillystrings.scanner import scan


@dataclass
class Source:
    name: str
    data: bytes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sillystrings",
        description="sillystrings - find the printable strings in a object, or other binary, file",
    )
    parser.add_argument(
        "files",
        metavar="FILE",
        nargs="+",
        type=argparse.FileType("rb"),
        help="the file(s) to search for printable strings",
    )
    parser.add_argument(
        "-n",
        "--bytes",
        metavar="NUM",
        dest="min_length",
        type=int,
        default=4,
        help="the minimum length of a string to be considered printable (default: 4)",
    )
    parser.add_argument(
        "-e",
        "--encoding",
        choices=("s", "S", "l", "b"),
        default="s",
        help="s=7-bit ASCII (default), S=8-bit, l=UTF-16 LE, b=UTF-16 BE",
    )
    parser.add_argument(
        "-w",
        "--include-whitespace",
        action="store_true",
        help="include all whitespace characters in the output strings",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"sillystrings {__version__}",
        help="show the version number and exit",
    )
    return parser


def format_offset(offset: int, radix: str | None) -> str:
    match radix:
        case "d":
            return f"{offset:7d} "
        case "o":
            return f"{offset:7o} "
        case "x":
            return f"{offset:7x} "
        case _:
            return ""


def main() -> None:
    args = build_parser().parse_args()

    sources: list[Source] = []

    if args.files:
        for f in args.files:
            sources.append(Source(f.name, f.read()))
            f.close()

    print(f"min_length: {args.min_length}")

    for source in sources:
        print(f"Source: {source.name} ({len(source.data) / (1024 * 1024):.1f} MB)")
        for offset, string in scan(
            source.data,
            min_length=args.min_length,
            encoding=args.encoding,
            include_whitespace=args.include_whitespace,
        ):
            print(f"{format_offset(offset, None)}{string}")


if __name__ == "__main__":
    main()
