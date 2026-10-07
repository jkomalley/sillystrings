from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    """A region of a binary that `-d` scans for strings.

    Attributes:
        name (str): The format's name for the section, such as "__DATA,__data".
            For tests and debugging only; nothing filters on it.
        offset (int): The section's first byte, as an offset from the start of
            the file.
        size (int): The section's length in bytes.
    """

    name: str
    offset: int
    size: int
