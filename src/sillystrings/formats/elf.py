"""ELF data sections, as GNU `strings -d` sees them.

The structs and constants below are transcribed from <elf.h>, in header order
and with the header's names, so each can be checked against it line by line;
tests/test_elf_constants.py also checks them against the real header with a C
compiler. The rules for which sections count as data come from GNU binutils
2.47 and cite the function they mirror.
"""

import functools
import struct
from dataclasses import dataclass
from typing import Annotated, NamedTuple, get_type_hints

from sillystrings.formats.common import Section

# --------------------------------------------------------------------------- #
# Constants from <elf.h>
# --------------------------------------------------------------------------- #

EI_NIDENT = 16  # elf.h: #define EI_NIDENT (16)
ELFMAG0 = 0x7F  # elf.h: #define ELFMAG0 0x7f
ELFMAG1 = ord("E")  # elf.h: #define ELFMAG1 'E'
ELFMAG2 = ord("L")  # elf.h: #define ELFMAG2 'L'
ELFMAG3 = ord("F")  # elf.h: #define ELFMAG3 'F'
ELFMAG = bytes([ELFMAG0, ELFMAG1, ELFMAG2, ELFMAG3])  # elf.h: #define ELFMAG "\177ELF"
SELFMAG = 4  # elf.h: #define SELFMAG 4
EI_CLASS = 4  # elf.h: #define EI_CLASS 4
ELFCLASS32 = 1  # elf.h: #define ELFCLASS32 1
ELFCLASS64 = 2  # elf.h: #define ELFCLASS64 2
EI_DATA = 5  # elf.h: #define EI_DATA 5
ELFDATA2LSB = 1  # elf.h: #define ELFDATA2LSB 1
ELFDATA2MSB = 2  # elf.h: #define ELFDATA2MSB 2
EI_VERSION = 6  # elf.h: #define EI_VERSION 6
EV_CURRENT = 1  # elf.h: #define EV_CURRENT 1

ET_EXEC = 2  # elf.h: #define ET_EXEC 2
ET_DYN = 3  # elf.h: #define ET_DYN 3
ET_CORE = 4  # elf.h: #define ET_CORE 4

SHN_UNDEF = 0  # elf.h: #define SHN_UNDEF 0
SHN_LORESERVE = 0xFF00  # elf.h: #define SHN_LORESERVE 0xff00
SHN_XINDEX = 0xFFFF  # elf.h: #define SHN_XINDEX 0xffff

SHT_NULL = 0  # elf.h: #define SHT_NULL 0
SHT_SYMTAB = 2  # elf.h: #define SHT_SYMTAB 2
SHT_STRTAB = 3  # elf.h: #define SHT_STRTAB 3
SHT_RELA = 4  # elf.h: #define SHT_RELA 4
SHT_NOTE = 7  # elf.h: #define SHT_NOTE 7
SHT_NOBITS = 8  # elf.h: #define SHT_NOBITS 8
SHT_REL = 9  # elf.h: #define SHT_REL 9
SHT_SHLIB = 10  # elf.h: #define SHT_SHLIB 10
SHT_SYMTAB_SHNDX = 18  # elf.h: #define SHT_SYMTAB_SHNDX 18

SHF_ALLOC = 1 << 1  # elf.h: #define SHF_ALLOC (1 << 1)
SHF_COMPRESSED = 1 << 11  # elf.h: #define SHF_COMPRESSED (1 << 11)

# --------------------------------------------------------------------------- #
# Structs from <elf.h>
#
# Each field is annotated with its struct format code: H = uint16_t
# (Elf32_Half, Elf64_Half), I = uint32_t (Elf32_Word, Elf32_Addr, Elf32_Off,
# Elf64_Word), Q = uint64_t (Elf64_Xword, Elf64_Addr, Elf64_Off),
# 16s = unsigned char[EI_NIDENT]. The byte order is chosen per file, from
# e_ident[EI_DATA]. The class names are the header's typedef names.
# --------------------------------------------------------------------------- #


class Elf32_Ehdr(NamedTuple):  # noqa: N801 -- the header's typedef name
    """elf.h: Elf32_Ehdr."""

    e_ident: Annotated[bytes, "16s"]  # unsigned char e_ident[EI_NIDENT]
    e_type: Annotated[int, "H"]  # Elf32_Half e_type
    e_machine: Annotated[int, "H"]  # Elf32_Half e_machine
    e_version: Annotated[int, "I"]  # Elf32_Word e_version
    e_entry: Annotated[int, "I"]  # Elf32_Addr e_entry
    e_phoff: Annotated[int, "I"]  # Elf32_Off e_phoff
    e_shoff: Annotated[int, "I"]  # Elf32_Off e_shoff
    e_flags: Annotated[int, "I"]  # Elf32_Word e_flags
    e_ehsize: Annotated[int, "H"]  # Elf32_Half e_ehsize
    e_phentsize: Annotated[int, "H"]  # Elf32_Half e_phentsize
    e_phnum: Annotated[int, "H"]  # Elf32_Half e_phnum
    e_shentsize: Annotated[int, "H"]  # Elf32_Half e_shentsize
    e_shnum: Annotated[int, "H"]  # Elf32_Half e_shnum
    e_shstrndx: Annotated[int, "H"]  # Elf32_Half e_shstrndx


class Elf64_Ehdr(NamedTuple):  # noqa: N801 -- the header's typedef name
    """elf.h: Elf64_Ehdr."""

    e_ident: Annotated[bytes, "16s"]  # unsigned char e_ident[EI_NIDENT]
    e_type: Annotated[int, "H"]  # Elf64_Half e_type
    e_machine: Annotated[int, "H"]  # Elf64_Half e_machine
    e_version: Annotated[int, "I"]  # Elf64_Word e_version
    e_entry: Annotated[int, "Q"]  # Elf64_Addr e_entry
    e_phoff: Annotated[int, "Q"]  # Elf64_Off e_phoff
    e_shoff: Annotated[int, "Q"]  # Elf64_Off e_shoff
    e_flags: Annotated[int, "I"]  # Elf64_Word e_flags
    e_ehsize: Annotated[int, "H"]  # Elf64_Half e_ehsize
    e_phentsize: Annotated[int, "H"]  # Elf64_Half e_phentsize
    e_phnum: Annotated[int, "H"]  # Elf64_Half e_phnum
    e_shentsize: Annotated[int, "H"]  # Elf64_Half e_shentsize
    e_shnum: Annotated[int, "H"]  # Elf64_Half e_shnum
    e_shstrndx: Annotated[int, "H"]  # Elf64_Half e_shstrndx


class Elf32_Shdr(NamedTuple):  # noqa: N801 -- the header's typedef name
    """elf.h: Elf32_Shdr."""

    sh_name: Annotated[int, "I"]  # Elf32_Word sh_name
    sh_type: Annotated[int, "I"]  # Elf32_Word sh_type
    sh_flags: Annotated[int, "I"]  # Elf32_Word sh_flags
    sh_addr: Annotated[int, "I"]  # Elf32_Addr sh_addr
    sh_offset: Annotated[int, "I"]  # Elf32_Off sh_offset
    sh_size: Annotated[int, "I"]  # Elf32_Word sh_size
    sh_link: Annotated[int, "I"]  # Elf32_Word sh_link
    sh_info: Annotated[int, "I"]  # Elf32_Word sh_info
    sh_addralign: Annotated[int, "I"]  # Elf32_Word sh_addralign
    sh_entsize: Annotated[int, "I"]  # Elf32_Word sh_entsize


class Elf64_Shdr(NamedTuple):  # noqa: N801 -- the header's typedef name
    """elf.h: Elf64_Shdr."""

    sh_name: Annotated[int, "I"]  # Elf64_Word sh_name
    sh_type: Annotated[int, "I"]  # Elf64_Word sh_type
    sh_flags: Annotated[int, "Q"]  # Elf64_Xword sh_flags
    sh_addr: Annotated[int, "Q"]  # Elf64_Addr sh_addr
    sh_offset: Annotated[int, "Q"]  # Elf64_Off sh_offset
    sh_size: Annotated[int, "Q"]  # Elf64_Xword sh_size
    sh_link: Annotated[int, "I"]  # Elf64_Word sh_link
    sh_info: Annotated[int, "I"]  # Elf64_Word sh_info
    sh_addralign: Annotated[int, "Q"]  # Elf64_Xword sh_addralign
    sh_entsize: Annotated[int, "Q"]  # Elf64_Xword sh_entsize


@functools.cache
def struct_format(cls: type[tuple]) -> str:
    """Join a struct's per-field format codes, in field order, with no byte order.

    Args:
        cls (type[tuple]): One of the NamedTuple structs above.

    Returns:
        str: The struct module format for the whole C struct.
    """
    # Annotations keep the order the fields were declared in
    hints = get_type_hints(cls, include_extras=True)
    return "".join(hint.__metadata__[0] for hint in hints.values())


def sizeof(cls: type[tuple]) -> int:
    """The size of a C struct in bytes, like C's sizeof.

    Args:
        cls (type[tuple]): One of the NamedTuple structs above.

    Returns:
        int: The struct's size, from its field formats.
    """
    # Standard sizes and no alignment padding: elf.h's headers have none
    return struct.calcsize("<" + struct_format(cls))


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

_Ehdr = Elf32_Ehdr | Elf64_Ehdr
_Shdr = Elf32_Shdr | Elf64_Shdr


@dataclass(frozen=True)
class _Layout:
    """The structs of one ELF variant: its class and byte order."""

    byte_order: str  # a struct module byte order: "<" or ">"
    ehdr: type[Elf32_Ehdr] | type[Elf64_Ehdr]
    shdr: type[Elf32_Shdr] | type[Elf64_Shdr]

    def read_ehdr(self, data: bytes | memoryview) -> _Ehdr:
        """Unpack the ELF header at the start of data."""
        return self.ehdr._make(self._unpack(self.ehdr, data, 0))

    def read_shdr(self, data: bytes | memoryview, offset: int) -> _Shdr:
        """Unpack the section header at offset."""
        return self.shdr._make(self._unpack(self.shdr, data, offset))

    def _unpack(self, cls: type[tuple], data: bytes | memoryview, offset: int) -> tuple:
        return struct.unpack_from(self.byte_order + struct_format(cls), data, offset)


# Keyed by (e_ident[EI_CLASS], e_ident[EI_DATA])
_LAYOUTS = {
    (ELFCLASS32, ELFDATA2LSB): _Layout("<", Elf32_Ehdr, Elf32_Shdr),
    (ELFCLASS32, ELFDATA2MSB): _Layout(">", Elf32_Ehdr, Elf32_Shdr),
    (ELFCLASS64, ELFDATA2LSB): _Layout("<", Elf64_Ehdr, Elf64_Shdr),
    (ELFCLASS64, ELFDATA2MSB): _Layout(">", Elf64_Ehdr, Elf64_Shdr),
}


def data_sections(data: bytes | memoryview) -> list[Section] | None:
    """List the sections of an ELF file that GNU `strings -d` scans.

    Args:
        data (bytes | memoryview): The whole file.

    Returns:
        list[Section] | None: The sections in section header order. None when
            the data is not an ELF object (core files included), its header or
            section header table is damaged, or BFD would reject it for a
            section name it cannot read or a note section outside the file. A
            section whose bytes lie outside the file is left out. This never
            raises on bad input.
    """
    layout = _ident(data)
    if layout is None or len(data) < sizeof(layout.ehdr):
        return None
    ehdr = layout.read_ehdr(data)
    # binutils 2.47 bfd/elfcode.h, elf_object_p: a core file is rejected as an
    # object (BFD opens it as bfd_core instead), so GNU scans it whole
    if ehdr.e_type == ET_CORE:
        return None
    # elf_object_p: with no section header table BFD makes no sections -- it
    # does not build them from the program headers -- so nothing is scanned
    if ehdr.e_shoff == 0 and ehdr.e_shnum == 0:
        return []
    headers = _section_headers(data, layout, ehdr)
    if headers is None:
        return None
    shstrndx = ehdr.e_shstrndx
    # Extended numbering: an index of SHN_LORESERVE or more is in section 0
    if shstrndx == SHN_XINDEX:
        shstrndx = headers[0].sh_link
    # elf_object_p: BFD resets a bad string table index to SHN_UNDEF, and
    # then builds no sections at all
    if (
        not SHN_UNDEF < shstrndx < len(headers)
        or headers[shstrndx].sh_type != SHT_STRTAB
    ):
        return []
    return _scan_sections(data, headers, ehdr.e_type, shstrndx)


def _ident(data: bytes | memoryview) -> _Layout | None:
    # e_ident: the magic, then the class, byte order and version bytes
    if len(data) < EI_NIDENT or bytes(data[:SELFMAG]) != ELFMAG:
        return None
    if data[EI_VERSION] != EV_CURRENT:
        return None
    return _LAYOUTS.get((data[EI_CLASS], data[EI_DATA]))


def _section_headers(
    data: bytes | memoryview, layout: _Layout, ehdr: _Ehdr
) -> list[_Shdr] | None:
    shdr_size = sizeof(layout.shdr)
    # binutils 2.47 bfd/elfcode.h, elf_object_p: the table must start past the
    # ELF header and hold entries of exactly the struct's size
    if ehdr.e_shoff < sizeof(layout.ehdr) or ehdr.e_shentsize != shdr_size:
        return None
    if ehdr.e_shoff + shdr_size > len(data):
        return None
    first = layout.read_shdr(data, ehdr.e_shoff)
    shnum = ehdr.e_shnum
    # Extended numbering: with SHN_LORESERVE or more sections, e_shnum is
    # SHN_UNDEF and the count is section 0's sh_size
    if shnum == SHN_UNDEF:
        shnum = first.sh_size
        if not SHN_UNDEF < shnum < SHN_LORESERVE:
            return None
    if ehdr.e_shoff + shnum * shdr_size > len(data):
        return None
    return [
        layout.read_shdr(data, ehdr.e_shoff + index * shdr_size)
        for index in range(shnum)
    ]


def _scan_sections(
    data: bytes | memoryview, headers: list[_Shdr], e_type: int, shstrndx: int
) -> list[Section] | None:
    names = _string_table(data, headers[shstrndx])
    # binutils 2.47 bfd/elf.c, bfd_section_from_shdr: BFD keeps the first
    # symbol table as the object's own; any later one is ignored, along with
    # its string table. With none, BFD looks up the string table of section 0,
    # which is never a string table, and so do we.
    symtab = next(
        (index for index, hdr in enumerate(headers) if hdr.sh_type == SHT_SYMTAB),
        SHN_UNDEF,
    )
    result: list[Section] = []
    for index, hdr in enumerate(headers):
        if index == SHN_UNDEF:
            continue
        name = _name(names, hdr.sh_name)
        # bfd_section_from_shdr looks up every section's name as it builds the
        # sections, and the object is rejected when one is unreadable
        if name is None:
            return None
        in_file = _in_file(data, hdr)
        # bfd/elf.c, _bfd_elf_make_section_from_shdr: BFD parses every note
        # section while opening the object, so a note it cannot read rejects
        # the whole object, not just the section
        if hdr.sh_type == SHT_NOTE and hdr.sh_size != 0 and not in_file:
            return None
        if not _is_data(headers, index, e_type, shstrndx, symtab):
            continue
        # binutils/strings.c, strings_a_section: GNU reports a section it
        # cannot read and scans the rest
        if not in_file:
            continue
        result.append(Section(name, hdr.sh_offset, hdr.sh_size))
    return result


def _is_data(
    headers: list[_Shdr], index: int, e_type: int, shstrndx: int, symtab: int
) -> bool:
    hdr = headers[index]
    # binutils 2.47 binutils/strings.c, strings_a_section: -d scans a section
    # only if its BFD flags include all of DATA_FLAGS (SEC_ALLOC | SEC_LOAD |
    # SEC_HAS_CONTENTS), and skips it if its size is 0.
    # bfd/elf.c, _bfd_elf_make_section_from_shdr: SEC_ALLOC is SHF_ALLOC;
    # SEC_LOAD and SEC_HAS_CONTENTS are any type but SHT_NOBITS -- the type
    # alone, not the offset. So code is scanned, and names never matter: BFD
    # only recognizes debug sections by name when they lack SHF_ALLOC.
    if not hdr.sh_flags & SHF_ALLOC or hdr.sh_type == SHT_NOBITS or hdr.sh_size == 0:
        return False
    # bfd/elf.c, bfd_section_from_shdr: the headers BFD makes no section from
    if hdr.sh_type in {SHT_NULL, SHT_SHLIB, SHT_SYMTAB_SHNDX}:
        return False
    if hdr.sh_type == SHT_SYMTAB:
        # A shared object may map its symbol table in, and only there does BFD
        # treat it as a section too
        return e_type == ET_DYN and index == symtab
    if hdr.sh_type == SHT_STRTAB:
        return index not in {shstrndx, headers[symtab].sh_link}
    if hdr.sh_type in {SHT_REL, SHT_RELA}:
        return not _is_attached_reloc(headers, hdr, e_type, symtab)
    return True


def _is_attached_reloc(
    headers: list[_Shdr], hdr: _Shdr, e_type: int, symtab: int
) -> bool:
    # binutils 2.47 bfd/elf.c, bfd_section_from_shdr: BFD folds a relocation
    # section into the section it applies to, rather than making a section of
    # it, when it can: outside executables and shared objects, for an
    # uncompressed section using the object's symbol table and naming a target
    # that is not itself relocations
    if e_type in {ET_EXEC, ET_DYN} or hdr.sh_flags & SHF_COMPRESSED:
        return False
    if hdr.sh_link == SHN_UNDEF or hdr.sh_link != symtab:
        return False
    if not SHN_UNDEF < hdr.sh_info < len(headers):
        return False
    return headers[hdr.sh_info].sh_type not in {SHT_REL, SHT_RELA}


def _in_file(data: bytes | memoryview, hdr: _Shdr) -> bool:
    return hdr.sh_offset + hdr.sh_size <= len(data)


# Section names are only for display and tests; nothing filters on them. So a
# name is cut at this many bytes rather than read to its terminator. Otherwise a
# damaged name table with no NULs would give every section its own copy of the
# rest of the table, quadratic in time and memory. Real names are far shorter,
# apart from some C++ -ffunction-sections names, which are only shortened.
NAME_LIMIT = 256


def _string_table(data: bytes | memoryview, hdr: _Shdr) -> bytes | None:
    # Copied once, rather than per name, since a damaged header can make the
    # table as large as the file. binutils 2.47 bfd/elf.c,
    # bfd_elf_get_str_section: BFD treats its last byte as the terminator,
    # whatever that byte holds, so it is left out.
    if hdr.sh_size == 0 or not _in_file(data, hdr):
        return None
    return bytes(data[hdr.sh_offset : hdr.sh_offset + hdr.sh_size - 1])


def _name(table: bytes | None, offset: int) -> str | None:
    # binutils 2.47 bfd/elf.c, bfd_elf_string_from_elf_section: offset 0 is
    # the empty name, which BFD resolves without reading the table
    if offset == 0:
        return ""
    # The terminator left out of the table is still a valid place to start
    if table is None or offset > len(table):
        return None
    # Read at most NAME_LIMIT bytes, stopping early at a NUL
    end = table.find(b"\0", offset, offset + NAME_LIMIT)
    return table[offset : offset + NAME_LIMIT if end == -1 else end].decode("latin-1")
