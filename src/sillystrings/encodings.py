from collections.abc import Iterator


def is_printable(byte: int, encoding: str, include_ws: bool = False) -> bool:
    """
    Check if a byte is printable in the given encoding.

    Only meaningful for 's' and 'S' modes. For UTF-16 modes ('l', 'b'),
    printability is determined by the byte pair inside iter_chars().

    Args:
        byte (int): The byte to check.
        encoding (str): The encoding to use for checking. Default is 'utf-8'.
        include_ws (bool): Whether to include whitespace characters as printable. Default is False.

    Returns:
        bool: True if the byte is printable, False otherwise.
    """
    if include_ws and byte in (0x09, 0x0A, 0x0D):  # Tab, LF, CR
        return True
    if encoding == "s":
        return 0x20 <= byte <= 0x7E
    elif encoding == "S":
        return 0x20 <= byte <= 0x7E or byte >= 0xA0
    return False


def iter_chars(
    data: bytes | memoryview, encoding: str, include_ws: bool = False
) -> Iterator[tuple[int, bool]]:
    """
    Iterate over the chars in a byte sequence, yielding their byte value and if they are printable.

    Args:
        data (bytes | memoryview): The byte sequence to iterate over.
        encoding (str): The encoding to use for checking printability.
        include_ws (bool): Whether to include whitespace characters as printable. Default is False.

    Yields:
        tuple[int, bool]: A tuple containing the byte value and a bool indicating if it's printable.
    """
    if encoding in ("s", "S"):
        for byte in data:
            yield byte, is_printable(byte, encoding, include_ws)
    elif encoding in ("l", "b"):
        for i in range(0, len(data) - 1, 2):
            char_bytes: bytes | memoryview[int] = data[i : i + 2]
            char_value: int = int.from_bytes(char_bytes, "little" if encoding == "l" else "big")
            yield char_value, is_printable(char_value, encoding, include_ws)
