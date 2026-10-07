# src/sillystrings/cli.py
import argparse
import contextlib
import mmap
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

from sillystrings.__version__ import __version__
from sillystrings.encodings import Encoding
from sillystrings.formats import data_ranges
from sillystrings.scanner import scan


def positive_int(value: str) -> int:
    """Parse a string as an integer of at least 1, for use as an argparse type.

    Args:
        value (str): The raw command-line argument.

    Returns:
        int: The parsed value.

    Raises:
        argparse.ArgumentTypeError: If the value is less than 1.
    """
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError(f"{value} is not a positive integer")
    return n


@dataclass
class Source:
    """A named blob of bytes to scan, from a file or from stdin."""

    name: str
    data: bytes | memoryview


@contextlib.contextmanager
def open_source(name: str) -> Iterator[Source]:
    """Open a file, or stdin for "-", as a Source valid for the with block.

    Files are memory-mapped rather than read, so the OS pages them in as the
    scan reaches them instead of the whole file being copied into memory.

    Args:
        name (str): A file path, or "-" for stdin.

    Yields:
        Source: The named data. A file's data is a view that is released when
            the block exits, so it must not be used afterwards.
    """
    if name == "-":
        # stdin may be a pipe, which cannot be mapped
        yield Source("<stdin>", sys.stdin.buffer.read())
        return
    with Path(name).open("rb") as f:
        if os.fstat(f.fileno()).st_size == 0:
            # mmap rejects empty files; read() also covers files like those in
            # /proc, which report a size of 0 but still have content
            yield Source(name, f.read())
            return
        with (
            mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mapped,
            # The scanner needs a buffer that iterates as ints; a bare mmap
            # iterates as one-byte bytes objects
            memoryview(mapped) as view,
        ):
            yield Source(name, view)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the sillystrings command-line interface.

    Returns:
        An instance of argparse.ArgumentParser configured with the appropriate
        arguments and options for the sillystrings CLI
    """
    parser = argparse.ArgumentParser(
        prog="sillystrings",
        description=(
            "sillystrings - find the printable strings in an object,"
            " or other binary, file"
        ),
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
        type=positive_int,
        default=4,
        help=(
            "Print sequences of displayable characters that are at least"
            " min-len characters long. If not specified a default minimum"
            " length of 4 is used. The distinction between displayable"
            " and non-displayable characters depends upon the setting of"
            " the -e option. Sequences are always terminated at"
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
        "-o",
        dest="radix",
        action="store_const",
        const="o",
        help="Like -t o. Print the offset within the file in octal.",
    )
    parser.add_argument(
        "-e",
        "--encoding",
        choices=get_args(Encoding),
        default="s",
        help=(
            "Select the character encoding of the strings that are to"
            " be found. Possible values for encoding are:"
            " s = single-7-bit-byte characters (default),"
            " S = single-8-bit-byte characters,"
            " b = 16-bit big-endian, l = 16-bit little-endian,"
            " B = 32-bit big-endian, L = 32-bit little-endian."
            " Useful for finding wide character strings. (l and b"
            " apply to, for example, Unicode UTF-16/UCS-2 encodings;"
            " L and B to UTF-32/UCS-4)."
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
        "-a",
        "--all",
        dest="data_only",
        action="store_const",
        const=False,
        default=False,
        help="Scan the whole file, whatever its format. This is the default.",
    )
    parser.add_argument(
        "-d",
        "--data",
        dest="data_only",
        action="store_const",
        const=True,
        help=(
            "Only scan the sections of an object file that are loaded into"
            " memory from the file, as GNU strings -d does: code and data, but"
            " not debug info or zero-filled sections. Thin Mach-O files are"
            " recognized. Any other file, including a fat Mach-O file, or one"
            " with no such sections, is scanned whole."
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
    """Format a byte offset for display in the requested radix.

    Args:
        offset (int): The byte offset of the string.
        radix (str | None): 'd' for decimal, 'o' for octal, 'x' for hex, or
            None to omit the offset.

    Returns:
        str: The padded offset followed by a space, or an empty string when
            no radix was requested.
    """
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
    """Run the sillystrings command-line interface.

    Raises:
        SystemExit: On a missing file, or when the output pipe closes early.
    """
    try:
        _run()
        # Output that fits in the stdout buffer is otherwise first written by
        # the interpreter's flush at shutdown, outside this handler, where a
        # closed pipe prints "Exception ignored" and exits 120 (#56). Every
        # source is closed by now, so no mapping is open when this raises.
        sys.stdout.flush()
    except BrokenPipeError:
        # A downstream reader went away -- `sillystrings big.bin | head` is the
        # normal case. Rebind stdout to devnull before exiting: the unwritten
        # data stays buffered, and the interpreter flushes stdout again during
        # shutdown, which would raise a second BrokenPipeError and print
        # "Exception ignored" after we are done.
        # If stdout has no underlying fd (captured or wrapped), there is no
        # real pipe to protect, so failing to rebind is not an error.
        with contextlib.suppress(OSError):
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(1)


def _run() -> None:
    """Parse arguments, then scan each source in turn and print what it finds."""
    args: argparse.Namespace = build_parser().parse_args()

    names: list[str] = args.files or ["-"]

    # Check every file before scanning any, so a bad path fails the run before
    # it prints partial output
    for name in names:
        if name != "-" and not Path(name).is_file():
            print(f"sillystrings: {name}: No such file", file=sys.stderr)
            sys.exit(1)

    multiple: bool = len(names) > 1

    # One source is open at a time, so peak memory does not grow with the
    # number of files
    for name in names:
        with open_source(name) as source, memoryview(source.data) as view:
            prefix = f"{source.name}: " if (multiple or args.print_file_name) else ""
            # GNU strings ignores -d for stdin and scans the stream whole
            data_only = args.data_only and name != "-"
            for start, size in _ranges(view, data_only=data_only):
                # Released explicitly, since a slice still alive when the block
                # exits -- as on a broken pipe -- stops the file being unmapped
                with view[start : start + size] as chunk:
                    for offset, string in scan(
                        chunk,
                        min_length=args.min_length,
                        encoding=args.encoding,
                        include_whitespace=args.include_all_whitespace,
                    ):
                        print(
                            f"{prefix}{format_offset(start + offset, args.radix)}"
                            f"{string}"
                        )


def _ranges(data: memoryview, *, data_only: bool) -> list[tuple[int, int]]:
    """Choose the (offset, size) byte ranges of a source to scan.

    Args:
        data (memoryview): The whole source.
        data_only (bool): Whether only the data sections were asked for, by -d.

    Returns:
        list[tuple[int, int]]: The data sections of a recognized object file
            under -d, otherwise the whole source.
    """
    ranges = data_ranges(data) if data_only else None
    return [(0, len(data))] if ranges is None else ranges


if __name__ == "__main__":
    main()
