"""Mach-O data sections, as GNU `strings -d` sees them.

The structs and constants below are transcribed from Apple's
<mach-o/loader.h>, in header order and with the header's names, so each can be
checked against it line by line; tests/test_macho_constants.py also checks them
against the real header with a C compiler. The rules for which sections count
as data come from GNU binutils 2.47 and cite the function they mirror.
"""

import struct
from dataclasses import dataclass
from typing import Annotated, NamedTuple

from sillystrings.formats.common import Section, sizeof, unpack

# --------------------------------------------------------------------------- #
# Constants from <mach-o/loader.h>
# --------------------------------------------------------------------------- #

MH_MAGIC = 0xFEEDFACE  # loader.h: #define MH_MAGIC 0xfeedface
MH_CIGAM = 0xCEFAEDFE  # loader.h: #define MH_CIGAM 0xcefaedfe
MH_MAGIC_64 = 0xFEEDFACF  # loader.h: #define MH_MAGIC_64 0xfeedfacf
MH_CIGAM_64 = 0xCFFAEDFE  # loader.h: #define MH_CIGAM_64 0xcffaedfe

LC_SEGMENT = 0x1  # loader.h: #define LC_SEGMENT 0x1
LC_SEGMENT_64 = 0x19  # loader.h: #define LC_SEGMENT_64 0x19

SECTION_TYPE = 0x000000FF  # loader.h: #define SECTION_TYPE 0x000000ff
S_ZEROFILL = 0x1  # loader.h: #define S_ZEROFILL 0x1
S_ATTR_DEBUG = 0x02000000  # loader.h: #define S_ATTR_DEBUG 0x02000000

# --------------------------------------------------------------------------- #
# Structs from <mach-o/loader.h>
#
# Each field is annotated with its struct format code: I = uint32_t,
# i = int32_t (cpu_type_t, cpu_subtype_t, vm_prot_t), Q = uint64_t,
# 16s = char[16]. The byte order is chosen per file, from its magic.
# --------------------------------------------------------------------------- #


class MachHeader(NamedTuple):
    """loader.h: struct mach_header."""

    magic: Annotated[int, "I"]  # uint32_t magic
    cputype: Annotated[int, "i"]  # cpu_type_t cputype
    cpusubtype: Annotated[int, "i"]  # cpu_subtype_t cpusubtype
    filetype: Annotated[int, "I"]  # uint32_t filetype
    ncmds: Annotated[int, "I"]  # uint32_t ncmds
    sizeofcmds: Annotated[int, "I"]  # uint32_t sizeofcmds
    flags: Annotated[int, "I"]  # uint32_t flags


class MachHeader64(NamedTuple):
    """loader.h: struct mach_header_64."""

    magic: Annotated[int, "I"]  # uint32_t magic
    cputype: Annotated[int, "i"]  # cpu_type_t cputype
    cpusubtype: Annotated[int, "i"]  # cpu_subtype_t cpusubtype
    filetype: Annotated[int, "I"]  # uint32_t filetype
    ncmds: Annotated[int, "I"]  # uint32_t ncmds
    sizeofcmds: Annotated[int, "I"]  # uint32_t sizeofcmds
    flags: Annotated[int, "I"]  # uint32_t flags
    reserved: Annotated[int, "I"]  # uint32_t reserved


class LoadCommand(NamedTuple):
    """loader.h: struct load_command."""

    cmd: Annotated[int, "I"]  # uint32_t cmd
    cmdsize: Annotated[int, "I"]  # uint32_t cmdsize


class SegmentCommand(NamedTuple):
    """loader.h: struct segment_command."""

    cmd: Annotated[int, "I"]  # uint32_t cmd
    cmdsize: Annotated[int, "I"]  # uint32_t cmdsize
    segname: Annotated[bytes, "16s"]  # char segname[16]
    vmaddr: Annotated[int, "I"]  # uint32_t vmaddr
    vmsize: Annotated[int, "I"]  # uint32_t vmsize
    fileoff: Annotated[int, "I"]  # uint32_t fileoff
    filesize: Annotated[int, "I"]  # uint32_t filesize
    maxprot: Annotated[int, "i"]  # vm_prot_t maxprot
    initprot: Annotated[int, "i"]  # vm_prot_t initprot
    nsects: Annotated[int, "I"]  # uint32_t nsects
    flags: Annotated[int, "I"]  # uint32_t flags


class SegmentCommand64(NamedTuple):
    """loader.h: struct segment_command_64."""

    cmd: Annotated[int, "I"]  # uint32_t cmd
    cmdsize: Annotated[int, "I"]  # uint32_t cmdsize
    segname: Annotated[bytes, "16s"]  # char segname[16]
    vmaddr: Annotated[int, "Q"]  # uint64_t vmaddr
    vmsize: Annotated[int, "Q"]  # uint64_t vmsize
    fileoff: Annotated[int, "Q"]  # uint64_t fileoff
    filesize: Annotated[int, "Q"]  # uint64_t filesize
    maxprot: Annotated[int, "i"]  # vm_prot_t maxprot
    initprot: Annotated[int, "i"]  # vm_prot_t initprot
    nsects: Annotated[int, "I"]  # uint32_t nsects
    flags: Annotated[int, "I"]  # uint32_t flags


class Section32(NamedTuple):
    """loader.h: struct section."""

    sectname: Annotated[bytes, "16s"]  # char sectname[16]
    segname: Annotated[bytes, "16s"]  # char segname[16]
    addr: Annotated[int, "I"]  # uint32_t addr
    size: Annotated[int, "I"]  # uint32_t size
    offset: Annotated[int, "I"]  # uint32_t offset
    align: Annotated[int, "I"]  # uint32_t align
    reloff: Annotated[int, "I"]  # uint32_t reloff
    nreloc: Annotated[int, "I"]  # uint32_t nreloc
    flags: Annotated[int, "I"]  # uint32_t flags
    reserved1: Annotated[int, "I"]  # uint32_t reserved1
    reserved2: Annotated[int, "I"]  # uint32_t reserved2


class Section64(NamedTuple):
    """loader.h: struct section_64."""

    sectname: Annotated[bytes, "16s"]  # char sectname[16]
    segname: Annotated[bytes, "16s"]  # char segname[16]
    addr: Annotated[int, "Q"]  # uint64_t addr
    size: Annotated[int, "Q"]  # uint64_t size
    offset: Annotated[int, "I"]  # uint32_t offset
    align: Annotated[int, "I"]  # uint32_t align
    reloff: Annotated[int, "I"]  # uint32_t reloff
    nreloc: Annotated[int, "I"]  # uint32_t nreloc
    flags: Annotated[int, "I"]  # uint32_t flags
    reserved1: Annotated[int, "I"]  # uint32_t reserved1
    reserved2: Annotated[int, "I"]  # uint32_t reserved2
    reserved3: Annotated[int, "I"]  # uint32_t reserved3


# --------------------------------------------------------------------------- #
# Rules from GNU binutils 2.47
# --------------------------------------------------------------------------- #

# bfd/mach-o.c, dwarf_section_names_xlat: the __DWARF sections BFD flags as
# SEC_DEBUGGING by name, whatever their own flags say -- and a dSYM's DWARF
# sections carry no S_ATTR_DEBUG. Newer DWARF sections missing from the table,
# such as __debug_str_offs, take the generic path in
# bfd_mach_o_init_section_from_mach_o and are loaded, so GNU strings -d scans
# them, and so do we.
BFD_DWARF_SECTIONS = frozenset(
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


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


_HeaderType = type[MachHeader] | type[MachHeader64]
_SegmentType = type[SegmentCommand] | type[SegmentCommand64]
_SectionType = type[Section32] | type[Section64]


@dataclass(frozen=True)
class _Layout:
    """The structs of one Mach-O variant: its word size and byte order."""

    byte_order: str  # a struct module byte order: "<" or ">"
    header: _HeaderType
    segment_cmd: int
    segment: _SegmentType
    section: _SectionType

    def read_header(self, data: bytes | memoryview) -> MachHeader | MachHeader64:
        """Unpack the mach_header at the start of data."""
        return self.header._make(unpack(self.header, self.byte_order, data, 0))

    def read_load_command(self, data: bytes | memoryview, offset: int) -> LoadCommand:
        """Unpack the load_command at offset."""
        return LoadCommand._make(unpack(LoadCommand, self.byte_order, data, offset))

    def read_segment(
        self, data: bytes | memoryview, offset: int
    ) -> SegmentCommand | SegmentCommand64:
        """Unpack the segment_command at offset."""
        return self.segment._make(unpack(self.segment, self.byte_order, data, offset))

    def read_section(
        self, data: bytes | memoryview, offset: int
    ) -> Section32 | Section64:
        """Unpack the section at offset."""
        return self.section._make(unpack(self.section, self.byte_order, data, offset))


_THIN = (MachHeader, LC_SEGMENT, SegmentCommand, Section32)
_THIN_64 = (MachHeader64, LC_SEGMENT_64, SegmentCommand64, Section64)

# The magic is read big-endian, so a big-endian file shows MH_MAGIC and a
# little-endian one shows it byte-swapped, as MH_CIGAM. Fat (universal) files
# are absent on purpose: BFD opens them as archives, not objects, so GNU
# strings -d scans them whole.
_MAGIC_FORMAT = ">I"  # uint32_t magic, the first field of every header
_LAYOUTS = {
    MH_MAGIC: _Layout(">", *_THIN),
    MH_CIGAM: _Layout("<", *_THIN),
    MH_MAGIC_64: _Layout(">", *_THIN_64),
    MH_CIGAM_64: _Layout("<", *_THIN_64),
}


def data_sections(data: bytes | memoryview) -> list[Section] | None:
    """List the sections of a thin Mach-O file that GNU `strings -d` scans.

    Args:
        data (bytes | memoryview): The whole file.

    Returns:
        list[Section] | None: The sections in load-command order. None when
            the data is not a thin Mach-O file or its header or load commands
            are damaged. A section whose bytes lie outside the file is left
            out. This never raises on bad input.
    """
    layout = _LAYOUTS.get(_magic(data))
    if layout is None or len(data) < sizeof(layout.header):
        return None
    header = layout.read_header(data)
    commands_end = sizeof(layout.header) + header.sizeofcmds
    if commands_end > len(data):
        return None

    result: list[Section] = []
    cmd_offset = sizeof(layout.header)
    for _ in range(header.ncmds):
        if cmd_offset + sizeof(LoadCommand) > commands_end:
            return None
        command = layout.read_load_command(data, cmd_offset)
        # A cmdsize too small to cover its own header would let the walk stall
        # or step backwards into the command it just read
        if (
            command.cmdsize < sizeof(LoadCommand)
            or cmd_offset + command.cmdsize > commands_end
        ):
            return None
        if command.cmd == layout.segment_cmd:
            segment = _segment_sections(data, cmd_offset, command.cmdsize, layout)
            if segment is None:
                return None
            result.extend(segment)
        cmd_offset += command.cmdsize
    return result


def _magic(data: bytes | memoryview) -> int | None:
    if len(data) < struct.calcsize(_MAGIC_FORMAT):
        return None
    return struct.unpack_from(_MAGIC_FORMAT, data)[0]


def _segment_sections(
    data: bytes | memoryview, cmd_offset: int, cmdsize: int, layout: _Layout
) -> list[Section] | None:
    if cmdsize < sizeof(layout.segment):
        return None
    segment = layout.read_segment(data, cmd_offset)
    # The section structs follow the segment command, inside its cmdsize
    first_section = cmd_offset + sizeof(layout.segment)
    if sizeof(layout.segment) + segment.nsects * sizeof(layout.section) > cmdsize:
        return None

    result: list[Section] = []
    for index in range(segment.nsects):
        offset = first_section + index * sizeof(layout.section)
        section = layout.read_section(data, offset)
        segname, sectname = _name(section.segname), _name(section.sectname)
        if not _is_data(segname, sectname, section):
            continue
        # GNU reports a section it cannot read and scans the rest, so a bad
        # section costs only itself, not the whole object
        if section.offset + section.size > len(data):
            continue
        result.append(Section(f"{segname},{sectname}", section.offset, section.size))
    return result


def _is_data(segname: str, sectname: str, section: Section32 | Section64) -> bool:
    # binutils 2.47 binutils/strings.c, strings_a_section: -d scans a section
    # only if its BFD flags include all of DATA_FLAGS (SEC_ALLOC | SEC_LOAD |
    # SEC_HAS_CONTENTS), and skips it if its size is 0
    if section.size == 0:
        return False
    # bfd/mach-o.c, bfd_mach_o_init_section_from_mach_o: SEC_HAS_CONTENTS is
    # set when the section's offset is nonzero -- not its size, which a dSYM
    # keeps for sections it has no bytes of
    if section.offset == 0:
        return False
    # bfd/mach-o.c, dwarf_section_names_xlat: these are SEC_DEBUGGING by name,
    # which is never loaded. Every other entry in BFD's name tables (mach-o.c
    # and the per-CPU mach-o-*.c) is SEC_LOAD, except (__DATA,__bss), whose
    # SEC_NO_FLAGS sends it through the rule below.
    if segname == "__DWARF" and sectname in BFD_DWARF_SECTIONS:
        return False
    # bfd/mach-o.c, bfd_mach_o_init_section_from_mach_o: a section BFD doesn't
    # know by name is SEC_DEBUGGING if S_ATTR_DEBUG is set, and otherwise
    # SEC_ALLOC, plus SEC_LOAD unless its type is S_ZEROFILL. Code is loaded,
    # so -d scans (__TEXT,__text). On real files, the name tables agree with
    # these flags.
    return (
        not section.flags & S_ATTR_DEBUG and section.flags & SECTION_TYPE != S_ZEROFILL
    )


def _name(raw: bytes) -> str:
    # loader.h: char sectname[16] / segname[16] are NUL-padded, with no
    # terminator when the name fills all 16 bytes
    return raw.split(b"\0", 1)[0].decode("latin-1")
