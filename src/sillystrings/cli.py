# src/sillystrings/cli.py
import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from sillystrings.__version__ import __version__
from sillystrings.scanner import scan


@dataclass
class Source:
    name: str
    data: bytes


def build_parser() -> argparse.ArgumentParser:
    """
    Build the argument parser for the sillystrings command-line interface.

    Returns:
        An instance of argparse.ArgumentParser configured with the appropriate arguments and options
        for the sillystrings CLI
    """
    parser = argparse.ArgumentParser(
        prog="sillystrings",
        description="sillystrings - find the printable strings in a object, or other binary, file",
    )
    parser.add_argument(
        "files",
        metavar="FILE",
        nargs="*",
        help="the file(s) to search for printable strings (use - for stdin)",
    )
    parser.add_argument(
        "-n",
        "--bytes",
        metavar="NUM",
        dest="min_length",
        type=int,
        default=4,
        help=(
            "Print sequences of displayable characters that are at least"
            " min-len characters long. If not specified a default minimum"
            " length of 4 is used. The distinction between displayable"
            " and non-displayable characters depends upon the setting of"
            " the -e and -U options. Sequences are always terminated at"
            " control characters such as new-line and carriage-return,"
            " but not the tab character."
        ),
    )
    parser.add_argument(
        "-t",
        "--radix",
        choices=("d", "o", "x"),
        help=(
            "Print the offset within the file before each string."
            " The single character argument specifies the radix of"
            " the offset - o for octal, x for hexadecimal, or d"
            " for decimal"
        ),
    )
    parser.add_argument(
        "-e",
        "--encoding",
        choices=("s", "S", "l", "b"),
        default="s",
        help=(
            "Select the character encoding of the strings that are to"
            " be found. Possible values for encoding are:"
            " s = single-7-bit-byte characters (default),"
            " S = single-8-bit-byte characters,"
            " b = 16-bit big-endian, l = 16-bit little-endian."
            " Useful for finding wide character strings. (l and b"
            " apply to, for example, Unicode UTF-16/UCS-2 encodings)."
        ),
    )
    parser.add_argument(
        "-w",
        "--include-all-whitespace",
        action="store_true",
        help=(
            "By default tab and space characters are included in the"
            " strings that are displayed, but other whitespace"
            " characters, such a newlines and carriage returns, are"
            " not. The -w option changes this so that all whitespace"
            " characters are considered to be part of a string."
        ),
    )
    parser.add_argument(
        "-f",
        "--print-file-name",
        action="store_true",
        help="Print the name of the file before each string.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"sillystrings {__version__}",
        help="Shows the version number and exits.",
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
    args: argparse.Namespace = build_parser().parse_args()

    sources: list[Source] = []

    if not args.files:
        sources.append(Source("<stdin>", sys.stdin.buffer.read()))
    else:
        for name in args.files:
            if name == "-":
                sources.append(Source("<stdin>", sys.stdin.buffer.read()))
            else:
                path = Path(name)
                if not path.is_file():
                    print(f"sillystrings: {name}: No such file", file=sys.stderr)
                    sys.exit(1)
                sources.append(Source(name, path.read_bytes()))

    multiple: bool = len(sources) > 1

    for source in sources:
        prefix = f"{source.name}: " if (multiple or args.print_file_name) else ""
        for offset, string in scan(
            source.data,
            min_length=args.min_length,
            encoding=args.encoding,
            include_whitespace=args.include_all_whitespace,
        ):
            print(f"{prefix}{format_offset(offset, args.radix)}{string}")


if __name__ == "__main__":
    main()
