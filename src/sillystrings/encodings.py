from collections.abc import Iterator


def is_printable(byte: int, encoding: str = "utf-8") -> bool:
    """
    Check if a byte is printable in the given encoding.

    Args:
        byte (int): The byte to check.
        encoding (str): The encoding to use for checking. Default is 'utf-8'.

    Returns:
        bool: True if the byte is printable, False otherwise.
    """
    try:
        char = bytes([byte]).decode(encoding)
        return char.isprintable()
    except UnicodeDecodeError:
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
    for byte in data:
        if include_ws:
            is_printable_char = is_printable(byte, encoding) or chr(byte).isspace()
        else:
            is_printable_char = is_printable(byte, encoding)
        yield byte, is_printable_char
