import functools
import struct
from dataclasses import dataclass
from typing import get_type_hints


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


# The format modules transcribe each C struct as a NamedTuple whose fields are
# annotated with their struct module format codes, as Annotated[int, "I"]. The
# helpers below turn those annotations into struct formats.


@functools.cache
def struct_format(cls: type[tuple]) -> str:
    """Join a struct's per-field format codes, in field order, with no byte order.

    Args:
        cls (type[tuple]): A NamedTuple struct from one of the format modules.

    Returns:
        str: The struct module format for the whole C struct.
    """
    # Annotations keep the order the fields were declared in
    hints = get_type_hints(cls, include_extras=True)
    return "".join(hint.__metadata__[0] for hint in hints.values())


def sizeof(cls: type[tuple]) -> int:
    """The size of a C struct in bytes, like C's sizeof.

    Args:
        cls (type[tuple]): A NamedTuple struct from one of the format modules.

    Returns:
        int: The struct's size, from its field formats.
    """
    # Standard sizes and no alignment padding: neither loader.h's nor elf.h's
    # structs have any
    return struct.calcsize("<" + struct_format(cls))


def unpack(
    cls: type[tuple], byte_order: str, data: bytes | memoryview, offset: int
) -> tuple:
    """Unpack the fields of the struct at offset, without bounds checks.

    Args:
        cls (type[tuple]): A NamedTuple struct from one of the format modules.
        byte_order (str): A struct module byte order: "<" or ">".
        data (bytes | memoryview): The whole file.
        offset (int): Where the struct starts. The caller checks it fits.

    Returns:
        tuple: The field values, in field order.
    """
    return struct.unpack_from(byte_order + struct_format(cls), data, offset)
