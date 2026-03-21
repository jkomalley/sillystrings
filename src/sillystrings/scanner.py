# src/sillystrings/scanner.py
from collections.abc import Iterator
from typing import Literal

from sillystrings.encodings import iter_chars


def scan(
    data: bytes | memoryview,
    *,
    min_length: int = 4,
    encoding: Literal["s", "S", "l", "b"] = "s",
    include_whitespace: bool = False,
) -> Iterator[tuple[int, str]]:
    """
    Scan a byte sequence for printable strings based on the specified encoding.

    Args:
        data (bytes | memoryview): The byte sequence to scan.
        min_length (int): The minimum length of strings to yield. Default is 4.
        encoding (Literal["s", "S", "l", "b"]): The encoding to use for scanning. Default is 's'.
            - 's' for 7-bit ASCII
            - 'S' for 8-bit extended ASCII
            - 'l' for UTF-16 little-endian
            - 'b' for UTF-16 big-endian
            Default is 's'
        include_whitespace (bool): Whether to include whitespace characters as part of the strings.
            Default is False.

    Yields:
        tuple[int, str]: The byte offset of the string's first byte, and the string itself.
    """
    if encoding in ("s", "S"):
        yield from _scan_ascii(
            data, min_length=min_length, encoding=encoding, include_whitespace=include_whitespace
        )
    elif encoding in ("l", "b"):
        yield from _scan_utf16(
            data, min_length=min_length, encoding=encoding, include_whitespace=include_whitespace
        )


def _scan_ascii(
    data: bytes | memoryview,
    *,
    min_length: int,
    encoding: str,
    include_whitespace: bool,
) -> Iterator[tuple[int, str]]:
    codec: Literal["latin-1", "ascii"] = "latin-1" if encoding == "S" else "ascii"
    acc = bytearray()
    acc_start = 0

    for offset, printable in iter_chars(data, encoding, include_whitespace):
        if printable:
            if not acc:
                acc_start = offset
            acc.append(data[offset])
        else:
            if len(acc) >= min_length:
                yield acc_start, acc.decode(codec)
            acc.clear()
    if len(acc) >= min_length:
        yield acc_start, acc.decode(codec)


def _scan_utf16(
    data: bytes | memoryview,
    *,
    min_length: int,
    encoding: str,
    include_whitespace: bool,
) -> Iterator[tuple[int, str]]:
    byteorder: Literal["little", "big"] = "little" if encoding == "l" else "big"
    acc: list[str] = []
    acc_start = 0

    for offset, printable in iter_chars(data, encoding, include_whitespace):
        if printable:
            if not acc:
                acc_start = offset
            ascii_value = int.from_bytes(data[offset : offset + 2], byteorder=byteorder)
            acc.append(chr(ascii_value))
        else:
            if len(acc) >= min_length:
                yield acc_start, "".join(acc)
            acc.clear()

    if len(acc) >= min_length:
        yield acc_start, "".join(acc)
