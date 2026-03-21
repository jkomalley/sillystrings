# src/sillystrings/encodings.py
from collections.abc import Iterator
from typing import Literal


def is_printable_ascii(byte: int, encoding: str = "s", include_ws: bool = False) -> bool:
    """
    Check if an ASCII value is printable.

    Args:
        byte (int): The byte to check.
        encoding (str): The encoding to use for checking. Default is 's' (7-bit ASCII).
        include_ws (bool): Whether to include whitespace characters as printable. Default is False.

    Returns:
        bool: True if the byte is printable, False otherwise.
    """
    if encoding not in ("s", "S"):
        return False
    if include_ws and byte in (0x09, 0x0A, 0x0D):  # Tab (\t), LF (\n), CR (\r)
        return True
    if encoding == "s":  # 7-bit ASCII
        return 0x20 <= byte <= 0x7E
    # "S": 8-bit extended ASCII
    return (0x20 <= byte <= 0x7E) or (0x80 <= byte <= 0xFF)


def is_printable_utf16(value: int, include_ws: bool = False) -> bool:
    """
    Check if a UTF-16 value is printable.
    Args:
        value (int): The UTF-16 value to check.
        include_ws (bool): Whether to include whitespace characters as printable. Default is False.
    Returns:
        bool: True if the UTF-16 value is printable, False otherwise.
    """
    if include_ws and value in (0x0009, 0x000A, 0x000D):
        return True
    return 0x0020 <= value <= 0x007E


def iter_chars(
    data: bytes | memoryview, encoding: str, include_ws: bool = False
) -> Iterator[tuple[int, bool]]:
    """
    Iterate over the chars in a byte sequence, yielding their byte offset and if they are printable.

    Args:
        data (bytes | memoryview): The byte sequence to iterate over.
        encoding (str): The encoding to use for checking printability.
        include_ws (bool): Whether to include whitespace characters as printable. Default is False.

    Yields:
        tuple[int, bool]: Tuple containing the byte offset and a bool indicating if it's printable.
    """
    if encoding in ("s", "S"):
        for i, byte in enumerate(data):
            yield i, is_printable_ascii(byte, encoding, include_ws)
    elif encoding in ("l", "b"):
        byteorder: Literal["little", "big"] = "little" if encoding == "l" else "big"
        for i in range(0, len(data) - 1, 2):
            char_bytes: bytes | memoryview = data[i : i + 2]
            char_value: int = int.from_bytes(bytes=char_bytes, byteorder=byteorder)
            yield i, is_printable_utf16(char_value, include_ws)
