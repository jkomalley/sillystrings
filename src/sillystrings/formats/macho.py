import struct
from dataclasses import dataclass

from sillystrings.formats.common import Section

_MAGIC = struct.Struct(">I")


@dataclass(frozen=True)
class _Layout:
    """Where the fields we read sit, for one word size and byte order."""

    header_size: int
    header: struct.Struct  # ncmds, sizeofcmds
    load_command: struct.Struct  # cmd, cmdsize
    segment_cmd: int
    segment_size: int  # bytes before the segment's section headers
    nsects: struct.Struct
    section: struct.Struct  # sectname, segname, size, offset, flags


def _layout(endian: str, *, is_64: bool) -> _Layout:
    if is_64:
        return _Layout(
            header_size=32,
            header=struct.Struct(f"{endian}16xII"),
            load_command=struct.Struct(f"{endian}II"),
            segment_cmd=0x19,  # LC_SEGMENT_64
            segment_size=72,
            nsects=struct.Struct(f"{endian}64xI"),
            section=struct.Struct(f"{endian}16s16s8xQI12xI12x"),
        )
    return _Layout(
        header_size=28,
        header=struct.Struct(f"{endian}16xII"),
        load_command=struct.Struct(f"{endian}II"),
        segment_cmd=0x1,  # LC_SEGMENT
        segment_size=56,
        nsects=struct.Struct(f"{endian}48xI"),
        section=struct.Struct(f"{endian}16s16s4xII12xI8x"),
    )


# Read as big-endian, so a little-endian file's magic comes out byte-swapped.
# Fat (universal) files are absent on purpose: BFD opens them as archives, not
# objects, so GNU strings -d scans them whole.
_LAYOUTS = {
    0xFEEDFACE: _layout(">", is_64=False),
    0xCEFAEDFE: _layout("<", is_64=False),
    0xFEEDFACF: _layout(">", is_64=True),
    0xCFFAEDFE: _layout("<", is_64=True),
}

_SECTION_TYPE = 0xFF
_S_ZEROFILL = 0x1
_S_ATTR_DEBUG = 0x02000000

# BFD treats these __DWARF sections as debug info by name, whatever their
# flags say -- and a dSYM's DWARF sections carry no debug attribute. Newer DWARF
# sections missing from BFD's table, such as __debug_str_offs, are loaded like
# any other section, so GNU strings -d scans them, and so do we.
_BFD_DWARF_SECTIONS = frozenset(
    {
        "__debug_frame",
        "__debug_info",
        "__debug_abbrev",
        "__debug_aranges",
        "__debug_macinfo",
        "__debug_line",
        "__debug_loc",
        "__debug_pubnames",
        "__debug_pubtypes",
        "__debug_str",
        "__debug_ranges",
        "__debug_macro",
        "__debug_gdb_scri",  # __debug_gdb_scripts, cut to 16 characters
    }
)


def data_sections(data: bytes | memoryview) -> list[Section] | None:
    """List the sections of a thin Mach-O file that GNU `strings -d` scans.

    Args:
        data (bytes | memoryview): The whole file.

    Returns:
        list[Section] | None: The sections in load-command order. None when
            the data is not a thin Mach-O file or is malformed in any way;
            this never raises on bad input.
    """
    layout = _LAYOUTS.get(_magic(data))
    if layout is None or len(data) < layout.header_size:
        return None
    ncmds, sizeofcmds = layout.header.unpack_from(data)
    commands_end = layout.header_size + sizeofcmds
    if commands_end > len(data):
        return None

    result: list[Section] = []
    cmd_offset = layout.header_size
    for _ in range(ncmds):
        if cmd_offset + layout.load_command.size > commands_end:
            return None
        cmd, cmdsize = layout.load_command.unpack_from(data, cmd_offset)
        # A cmdsize too small to cover its own header would let the walk stall
        # or step backwards into the command it just read
        if cmdsize < layout.load_command.size or cmd_offset + cmdsize > commands_end:
            return None
        if cmd == layout.segment_cmd:
            segment = _segment_sections(data, cmd_offset, cmdsize, layout)
            if segment is None:
                return None
            result.extend(segment)
        cmd_offset += cmdsize
    return result


def _magic(data: bytes | memoryview) -> int | None:
    if len(data) < _MAGIC.size:
        return None
    return _MAGIC.unpack_from(data)[0]


def _segment_sections(
    data: bytes | memoryview, cmd_offset: int, cmdsize: int, layout: _Layout
) -> list[Section] | None:
    if cmdsize < layout.segment_size:
        return None
    (nsects,) = layout.nsects.unpack_from(data, cmd_offset)
    if layout.segment_size + nsects * layout.section.size > cmdsize:
        return None

    result: list[Section] = []
    for index in range(nsects):
        sectname, segname, size, offset, flags = layout.section.unpack_from(
            data, cmd_offset + layout.segment_size + index * layout.section.size
        )
        segment_name, section_name = _name(segname), _name(sectname)
        if not _is_data(segment_name, section_name, size, offset, flags):
            continue
        if offset + size > len(data):
            return None
        result.append(Section(f"{segment_name},{section_name}", offset, size))
    return result


def _is_data(segname: str, sectname: str, size: int, offset: int, flags: int) -> bool:
    # GNU strings -d scans a section only if BFD marks it ALLOC, LOAD and
    # HAS_CONTENTS, and it is not empty. BFD's Mach-O reader gives a section
    # contents when its offset is nonzero -- not its size, which a dSYM keeps
    # for sections it has no bytes of -- and loads it unless it is debug info
    # or S_ZEROFILL. Code sections like (__TEXT,__text) are loaded, so -d
    # scans them. BFD also assigns flags by name from a table of well-known
    # sections; apart from the DWARF ones, every entry there is loaded and
    # matches the section's own type on real files.
    if segname == "__DWARF" and sectname in _BFD_DWARF_SECTIONS:
        return False
    return (
        size != 0
        and offset != 0
        and not flags & _S_ATTR_DEBUG
        and flags & _SECTION_TYPE != _S_ZEROFILL
    )


def _name(raw: bytes) -> str:
    # NUL-padded to 16 bytes, with no terminator when the name fills them all
    return raw.split(b"\0", 1)[0].decode("latin-1")
