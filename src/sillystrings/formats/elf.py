import struct
from dataclasses import dataclass

from sillystrings.formats.common import Section

# elf.h: #define ELFMAG "\177ELF", at e_ident[EI_MAG0..EI_MAG3]
_ELFMAG = b"\x7fELF"
# elf.h: #define EI_NIDENT (16)
_EI_NIDENT = 16
# elf.h: #define EI_CLASS 4, EI_DATA 5, EI_VERSION 6 (indexes into e_ident)
_EI_CLASS = 4
_EI_DATA = 5
_EI_VERSION = 6
# elf.h: #define ELFCLASS32 1, ELFCLASS64 2
_ELFCLASS32 = 1
_ELFCLASS64 = 2
# elf.h: #define ELFDATA2LSB 1, ELFDATA2MSB 2
_ELFDATA2LSB = 1
_ELFDATA2MSB = 2
# elf.h: #define EV_CURRENT 1
_EV_CURRENT = 1

# elf.h: #define ET_EXEC 2, ET_DYN 3, ET_CORE 4 (values of e_type)
_ET_EXEC = 2
_ET_DYN = 3
_ET_CORE = 4

# elf.h: #define SHN_UNDEF 0, SHN_LORESERVE 0xff00, SHN_XINDEX 0xffff
_SHN_UNDEF = 0
_SHN_LORESERVE = 0xFF00
_SHN_XINDEX = 0xFFFF

# elf.h: #define SHT_NULL 0, SHT_SYMTAB 2, SHT_STRTAB 3, SHT_RELA 4, SHT_NOTE 7,
# SHT_NOBITS 8, SHT_REL 9, SHT_SHLIB 10, SHT_SYMTAB_SHNDX 18 (values of sh_type)
_SHT_NULL = 0
_SHT_SYMTAB = 2
_SHT_STRTAB = 3
_SHT_RELA = 4
_SHT_NOTE = 7
_SHT_NOBITS = 8
_SHT_REL = 9
_SHT_SHLIB = 10
_SHT_SYMTAB_SHNDX = 18

# elf.h: #define SHF_ALLOC (1 << 1), SHF_COMPRESSED (1 << 11) (bits of sh_flags)
_SHF_ALLOC = 1 << 1
_SHF_COMPRESSED = 1 << 11


@dataclass(frozen=True)
class _Layout:
    """The header structs of one word size and byte order."""

    ehdr: struct.Struct  # Elf32_Ehdr / Elf64_Ehdr, after e_ident
    shdr: struct.Struct  # Elf32_Shdr / Elf64_Shdr


def _layout(endian: str, *, is_64: bool) -> _Layout:
    # elf.h: Elf{32,64}_Ehdr is e_ident[16], e_type, e_machine (Elf_Half),
    # e_version (Elf_Word), e_entry (Addr), e_phoff, e_shoff (Off), e_flags
    # (Word), e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx
    # (Half). Elf{32,64}_Shdr is sh_name, sh_type (Word), sh_flags (Word / Xword),
    # sh_addr (Addr), sh_offset (Off), sh_size (Word / Xword), sh_link, sh_info
    # (Word), sh_addralign, sh_entsize (Word / Xword). Addr, Off and Xword are
    # 4 bytes in ELF32 and 8 in ELF64; Half is 2 and Word is 4 in both.
    word = "Q" if is_64 else "I"
    return _Layout(
        ehdr=struct.Struct(f"{endian}{_EI_NIDENT}xHHI{word * 3}IHHHHHH"),
        shdr=struct.Struct(f"{endian}II{word * 4}II{word * 2}"),
    )


# Keyed by (e_ident[EI_CLASS], e_ident[EI_DATA])
_LAYOUTS = {
    (_ELFCLASS32, _ELFDATA2LSB): _layout("<", is_64=False),
    (_ELFCLASS32, _ELFDATA2MSB): _layout(">", is_64=False),
    (_ELFCLASS64, _ELFDATA2LSB): _layout("<", is_64=True),
    (_ELFCLASS64, _ELFDATA2MSB): _layout(">", is_64=True),
}


@dataclass(frozen=True)
class _Shdr:
    """The section header fields the data rule reads."""

    name: int
    type: int
    flags: int
    offset: int
    size: int
    link: int
    info: int


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
    if layout is None or len(data) < _EI_NIDENT + layout.ehdr.size:
        return None
    (e_type, _, _, _, _, e_shoff, _, _, _, _, e_shentsize, e_shnum, e_shstrndx) = (
        layout.ehdr.unpack_from(data)
    )
    # BFD opens a core file as bfd_core, not bfd_object, so GNU scans it whole
    if e_type == _ET_CORE:
        return None
    # No section header table: BFD makes no sections from the program headers,
    # so there is nothing to scan
    if e_shoff == 0 and e_shnum == 0:
        return []
    headers = _section_headers(data, layout, e_shoff, e_shentsize, e_shnum)
    if headers is None:
        return None
    if e_shstrndx == _SHN_XINDEX:
        e_shstrndx = headers[0].link
    # BFD resets a bad string table index to SHN_UNDEF, and then builds no
    # sections at all (binutils bfd/elfcode.h elf_object_p)
    if (
        not _SHN_UNDEF < e_shstrndx < len(headers)
        or headers[e_shstrndx].type != _SHT_STRTAB
    ):
        return []
    return _scan_sections(data, headers, e_type, e_shstrndx)


def _ident(data: bytes | memoryview) -> _Layout | None:
    if len(data) < _EI_NIDENT or bytes(data[: len(_ELFMAG)]) != _ELFMAG:
        return None
    if data[_EI_VERSION] != _EV_CURRENT:
        return None
    return _LAYOUTS.get((data[_EI_CLASS], data[_EI_DATA]))


def _section_headers(
    data: bytes | memoryview,
    layout: _Layout,
    e_shoff: int,
    e_shentsize: int,
    e_shnum: int,
) -> list[_Shdr] | None:
    # The table must start past the ELF header and hold entries of exactly the
    # size BFD expects (binutils bfd/elfcode.h elf_object_p)
    header_size = _EI_NIDENT + layout.ehdr.size
    if e_shoff < header_size or e_shentsize != layout.shdr.size:
        return None
    if e_shoff + layout.shdr.size > len(data):
        return None
    first = _read_shdr(data, layout, e_shoff)
    # Extended numbering: with SHN_LORESERVE or more sections, e_shnum is 0 and
    # the count is section 0's sh_size
    if e_shnum == _SHN_UNDEF:
        e_shnum = first.size
        if not 0 < e_shnum < _SHN_LORESERVE:
            return None
    if e_shoff + e_shnum * layout.shdr.size > len(data):
        return None
    return [
        _read_shdr(data, layout, e_shoff + index * layout.shdr.size)
        for index in range(e_shnum)
    ]


def _read_shdr(data: bytes | memoryview, layout: _Layout, offset: int) -> _Shdr:
    name, type_, flags, _, sh_offset, size, link, info, _, _ = layout.shdr.unpack_from(
        data, offset
    )
    return _Shdr(name, type_, flags, sh_offset, size, link, info)


def _scan_sections(
    data: bytes | memoryview, headers: list[_Shdr], e_type: int, e_shstrndx: int
) -> list[Section] | None:
    names = _string_table(data, headers[e_shstrndx])
    # BFD keeps the first symbol table as the object's own; any later one is
    # ignored, along with its string table. With none, BFD looks up the string
    # table of section 0, which is never a string table, and so do we.
    symtab = next(
        (index for index, hdr in enumerate(headers) if hdr.type == _SHT_SYMTAB),
        _SHN_UNDEF,
    )
    result: list[Section] = []
    for index, hdr in enumerate(headers):
        if index == _SHN_UNDEF:
            continue
        name = _name(names, hdr.name)
        # BFD looks up every section's name as it builds the sections, and
        # rejects the object when one is unreadable
        if name is None:
            return None
        in_file = _in_file(data, hdr)
        # BFD parses every note section while opening the object, so a note it
        # cannot read rejects the whole object, not just the section
        if hdr.type == _SHT_NOTE and hdr.size != 0 and not in_file:
            return None
        if not _is_data(headers, index, e_type, e_shstrndx, symtab):
            continue
        # GNU reports a section it cannot read and scans the rest
        if not in_file:
            continue
        result.append(Section(name, hdr.offset, hdr.size))
    return result


def _is_data(
    headers: list[_Shdr], index: int, e_type: int, e_shstrndx: int, symtab: int
) -> bool:
    # GNU strings -d scans a section only if BFD marks it ALLOC, LOAD and
    # HAS_CONTENTS, and it is not empty. For ELF that is SHF_ALLOC on any type
    # but SHT_NOBITS (binutils bfd/elf.c _bfd_elf_make_section_from_shdr), so
    # code is scanned. Names don't matter: BFD only recognizes debug sections
    # by name when they lack SHF_ALLOC. What remains is the headers BFD never
    # makes a section from (bfd/elf.c bfd_section_from_shdr).
    hdr = headers[index]
    if not hdr.flags & _SHF_ALLOC or hdr.type == _SHT_NOBITS or hdr.size == 0:
        return False
    if hdr.type in {_SHT_NULL, _SHT_SHLIB, _SHT_SYMTAB_SHNDX}:
        return False
    if hdr.type == _SHT_SYMTAB:
        # A shared object may map its symbol table in, and only there does BFD
        # treat it as a section too
        return e_type == _ET_DYN and index == symtab
    if hdr.type == _SHT_STRTAB:
        return index not in {e_shstrndx, headers[symtab].link}
    if hdr.type in {_SHT_REL, _SHT_RELA}:
        return not _is_attached_reloc(headers, hdr, e_type, symtab)
    return True


def _is_attached_reloc(
    headers: list[_Shdr], hdr: _Shdr, e_type: int, symtab: int
) -> bool:
    # BFD folds a relocation section into the section it applies to, rather
    # than making a section of it, when it can: outside executables and shared
    # objects, for an uncompressed section using the object's symbol table and
    # naming a target that is not itself relocations
    if e_type in {_ET_EXEC, _ET_DYN} or hdr.flags & _SHF_COMPRESSED:
        return False
    if hdr.link == _SHN_UNDEF or hdr.link != symtab:
        return False
    if not _SHN_UNDEF < hdr.info < len(headers):
        return False
    return headers[hdr.info].type not in {_SHT_REL, _SHT_RELA}


def _in_file(data: bytes | memoryview, hdr: _Shdr) -> bool:
    return hdr.offset + hdr.size <= len(data)


def _string_table(data: bytes | memoryview, hdr: _Shdr) -> bytes | None:
    # Copied once, rather than per name, since a damaged header can make the
    # table as large as the file. BFD treats its last byte as the terminator,
    # whatever that byte holds, so it is left out.
    if hdr.size == 0 or not _in_file(data, hdr):
        return None
    return bytes(data[hdr.offset : hdr.offset + hdr.size - 1])


def _name(table: bytes | None, offset: int) -> str | None:
    # Offset 0 is the empty name, which BFD resolves without reading the table
    if offset == 0:
        return ""
    # The terminator left out of the table is still a valid place to start
    if table is None or offset > len(table):
        return None
    end = table.find(b"\0", offset)
    return table[offset : None if end == -1 else end].decode("latin-1")
