# src/sillystrings/encodings.py
from collections.abc import Iterator
from typing import Literal

Encoding = Literal["s", "S", "l", "b", "L", "B"]
"""The encodings sillystrings can scan for, in `strings`' own -e vocabulary."""

ASCII_ENCODINGS = ("s", "S")

WIDE_ENCODINGS: dict[str, tuple[int, Literal["little", "big"]]] = {
    "l": (2, "little"),
    "b": (2, "big"),
    "L": (4, "little"),
    "B": (4, "big"),
}
"""The multi-byte encodings, mapped to their character width and byte order."""


TAB = 0x09
"""Tab is printable by default, matching GNU strings, so it never ends a string."""

OTHER_WHITESPACE = range(0x0A, 0x0E)
"""Newline, vertical tab, form feed, and carriage return: the rest of C's isspace
set. GNU strings -w treats them as printable; by default they end a string."""


def unsupported_encoding(encoding: str) -> ValueError:
    """Build the error for an encoding outside the supported vocabulary.

    Args:
        encoding (str): The rejected encoding.

    Returns:
        ValueError: The error to raise.
    """
    return ValueError(f"unsupported encoding: {encoding}")


def is_printable_ascii(
    byte: int, encoding: str = "s", *, include_ws: bool = False
) -> bool:
    """Check if an ASCII value is printable.

    Args:
        byte (int): The byte to check.
        encoding (str): The encoding to use for checking. Default is 's'
            (7-bit ASCII).
        include_ws (bool): Whether to also treat newline, vertical tab, form
            feed, and carriage return as printable. Tab is always printable.
            Default is False.

    Returns:
        bool: True if the byte is printable, False otherwise.
    """
    if encoding not in ("s", "S"):
        return False
    if byte == TAB or (include_ws and byte in OTHER_WHITESPACE):
        return True
    if encoding == "s":  # 7-bit ASCII
        return 0x20 <= byte <= 0x7E
    # "S": 8-bit extended ASCII
    return (0x20 <= byte <= 0x7E) or (0x80 <= byte <= 0xFF)


def is_printable_wide(value: int, *, include_ws: bool = False) -> bool:
    """Check if a multi-byte character value is printable.

    Args:
        value (int): The decoded character value to check.
        include_ws (bool): Whether to also treat newline, vertical tab, form
            feed, and carriage return as printable. Tab is always printable.
            Default is False.

    Returns:
        bool: True if the character value is printable, False otherwise.
    """
    if value == TAB or (include_ws and value in OTHER_WHITESPACE):
        return True
    return 0x0020 <= value <= 0x007E


def iter_chars(
    data: bytes | memoryview, encoding: str, *, include_ws: bool = False
) -> Iterator[tuple[int, bool]]:
    """Iterate over the chars in a byte sequence, yielding offset and printability.

    Args:
        data (bytes | memoryview): The byte sequence to iterate over.
        encoding (str): The encoding to use for checking printability.
        include_ws (bool): Whether to include whitespace characters as
            printable. Default is False.

    Yields:
        tuple[int, bool]: Tuple containing the byte offset and a bool
            indicating if it's printable.

    Raises:
        ValueError: If the encoding is not an Encoding member.
    """
    if encoding in ASCII_ENCODINGS:
        # The answer depends only on the byte once encoding and include_ws are
        # fixed, so compute all 256 up front and keep the per-byte loop in C.
        table = tuple(
            is_printable_ascii(b, encoding, include_ws=include_ws) for b in range(256)
        )
        yield from enumerate(map(table.__getitem__, data))
    elif encoding in WIDE_ENCODINGS:
        width, byteorder = WIDE_ENCODINGS[encoding]
        # A trailing partial character is never yielded, so it cannot start a run
        for i in range(0, len(data) - width + 1, width):
            char_value = int.from_bytes(data[i : i + width], byteorder=byteorder)
            yield i, is_printable_wide(char_value, include_ws=include_ws)
    else:
        raise unsupported_encoding(encoding)
