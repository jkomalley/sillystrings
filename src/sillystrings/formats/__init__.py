from collections.abc import Callable

from sillystrings.formats import macho
from sillystrings.formats.common import Section

# Each parser returns None for data that is not its format, so the first one
# to return a list owns the file. A new format is one more entry here.
_PARSERS: tuple[Callable[[bytes | memoryview], list[Section] | None], ...] = (
    macho.data_sections,
)


def data_ranges(data: bytes | memoryview) -> list[tuple[int, int]] | None:
    """Find the byte ranges of a binary that GNU `strings -d` would scan.

    Args:
        data (bytes | memoryview): The whole file.

    Returns:
        list[tuple[int, int]] | None: The `(offset, size)` of each data
            section, in the order the format lists them, with offsets from the
            start of the file. None when the whole file should be scanned
            instead: no parser recognizes the data, its structure is
            damaged, or it has no data sections that lie within the file.
    """
    for parse in _PARSERS:
        sections = parse(data)
        if sections is not None:
            # GNU strings falls back to the whole file when no section qualified
            # -- a parsed object with nothing to scan is treated as no object
            if not sections:
                return None
            return [(section.offset, section.size) for section in sections]
    return None
