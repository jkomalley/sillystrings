# tests/conftest.py
import itertools
import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

# encoding -> (codec for str segments, bytes per NUL character for int segments)
_LAYOUTS = {
    "s": ("ascii", 1),
    "S": ("ascii", 1),
    "l": ("utf-16-le", 2),
    "b": ("utf-16-be", 2),
    "L": ("utf-32-le", 4),
    "B": ("utf-32-be", 4),
}


def make_data(segments: list[str | int | bytes], encoding: str) -> bytes:
    codec, width = _LAYOUTS[encoding]
    result = bytearray()
    for segment in segments:
        if isinstance(segment, bytes):
            result += segment
        elif isinstance(segment, str):
            result += segment.encode(codec)
        else:
            result += b"\x00" * width * segment
    return bytes(result)


@dataclass(frozen=True)
class MachOSection:
    segname: str
    sectname: str
    content: bytes = b""
    flags: int = 0
    # Override the header fields, which otherwise describe content as placed
    size: int | None = None
    offset: int | None = None


# --- Mach-O, transcribed from <mach-o/loader.h> ---
#
# Deliberately independent of sillystrings.formats.macho -- nothing is shared --
# so a field or constant the parser gets wrong cannot be wrong the same way
# here. tests/test_macho_constants.py checks both against the real header.

MH_MAGIC = 0xFEEDFACE  # loader.h: #define MH_MAGIC 0xfeedface
MH_MAGIC_64 = 0xFEEDFACF  # loader.h: #define MH_MAGIC_64 0xfeedfacf
MH_OBJECT = 0x1  # loader.h: #define MH_OBJECT 0x1
LC_SEGMENT = 0x1  # loader.h: #define LC_SEGMENT 0x1
LC_SYMTAB = 0x2  # loader.h: #define LC_SYMTAB 0x2
LC_SEGMENT_64 = 0x19  # loader.h: #define LC_SEGMENT_64 0x19
S_ZEROFILL = 0x1  # loader.h: #define S_ZEROFILL 0x1
S_GB_ZEROFILL = 0xC  # loader.h: #define S_GB_ZEROFILL 0xc
S_THREAD_LOCAL_ZEROFILL = 0x12  # loader.h: #define S_THREAD_LOCAL_ZEROFILL 0x12
S_ATTR_PURE_INSTRUCTIONS = 0x80000000  # loader.h: #define S_ATTR_PURE_INSTRUCTIONS
S_ATTR_DEBUG = 0x02000000  # loader.h: #define S_ATTR_DEBUG 0x02000000

# Each struct as (field name, struct format code), in header order:
# I = uint32_t, i = int32_t (cpu_type_t, cpu_subtype_t, vm_prot_t),
# Q = uint64_t, 16s = char[16]
Fields = list[tuple[str, str]]

MACH_HEADER: Fields = [  # struct mach_header
    ("magic", "I"),  # uint32_t
    ("cputype", "i"),  # cpu_type_t
    ("cpusubtype", "i"),  # cpu_subtype_t
    ("filetype", "I"),  # uint32_t
    ("ncmds", "I"),  # uint32_t
    ("sizeofcmds", "I"),  # uint32_t
    ("flags", "I"),  # uint32_t
]
MACH_HEADER_64: Fields = [  # struct mach_header_64
    ("magic", "I"),  # uint32_t
    ("cputype", "i"),  # cpu_type_t
    ("cpusubtype", "i"),  # cpu_subtype_t
    ("filetype", "I"),  # uint32_t
    ("ncmds", "I"),  # uint32_t
    ("sizeofcmds", "I"),  # uint32_t
    ("flags", "I"),  # uint32_t
    ("reserved", "I"),  # uint32_t
]
SEGMENT_COMMAND: Fields = [  # struct segment_command
    ("cmd", "I"),  # uint32_t
    ("cmdsize", "I"),  # uint32_t
    ("segname", "16s"),  # char[16]
    ("vmaddr", "I"),  # uint32_t
    ("vmsize", "I"),  # uint32_t
    ("fileoff", "I"),  # uint32_t
    ("filesize", "I"),  # uint32_t
    ("maxprot", "i"),  # vm_prot_t
    ("initprot", "i"),  # vm_prot_t
    ("nsects", "I"),  # uint32_t
    ("flags", "I"),  # uint32_t
]
SEGMENT_COMMAND_64: Fields = [  # struct segment_command_64
    ("cmd", "I"),  # uint32_t
    ("cmdsize", "I"),  # uint32_t
    ("segname", "16s"),  # char[16]
    ("vmaddr", "Q"),  # uint64_t
    ("vmsize", "Q"),  # uint64_t
    ("fileoff", "Q"),  # uint64_t
    ("filesize", "Q"),  # uint64_t
    ("maxprot", "i"),  # vm_prot_t
    ("initprot", "i"),  # vm_prot_t
    ("nsects", "I"),  # uint32_t
    ("flags", "I"),  # uint32_t
]
SECTION: Fields = [  # struct section
    ("sectname", "16s"),  # char[16]
    ("segname", "16s"),  # char[16]
    ("addr", "I"),  # uint32_t
    ("size", "I"),  # uint32_t
    ("offset", "I"),  # uint32_t
    ("align", "I"),  # uint32_t
    ("reloff", "I"),  # uint32_t
    ("nreloc", "I"),  # uint32_t
    ("flags", "I"),  # uint32_t
    ("reserved1", "I"),  # uint32_t
    ("reserved2", "I"),  # uint32_t
]
SECTION_64: Fields = [  # struct section_64
    ("sectname", "16s"),  # char[16]
    ("segname", "16s"),  # char[16]
    ("addr", "Q"),  # uint64_t
    ("size", "Q"),  # uint64_t
    ("offset", "I"),  # uint32_t
    ("align", "I"),  # uint32_t
    ("reloff", "I"),  # uint32_t
    ("nreloc", "I"),  # uint32_t
    ("flags", "I"),  # uint32_t
    ("reserved1", "I"),  # uint32_t
    ("reserved2", "I"),  # uint32_t
    ("reserved3", "I"),  # uint32_t
]
SYMTAB_COMMAND: Fields = [  # struct symtab_command
    ("cmd", "I"),  # uint32_t
    ("cmdsize", "I"),  # uint32_t
    ("symoff", "I"),  # uint32_t
    ("nsyms", "I"),  # uint32_t
    ("stroff", "I"),  # uint32_t
    ("strsize", "I"),  # uint32_t
]


def sizeof(fields: Fields) -> int:
    # Standard sizes and no alignment padding, which loader.h's structs lack
    return struct.calcsize("<" + "".join(code for _, code in fields))


def offsetof(fields: Fields, name: str) -> int:
    names = [field for field, _ in fields]
    return sizeof(fields[: names.index(name)])


def _pack(fields: Fields, endian: str, **values: int | bytes) -> bytes:
    """Pack a struct by field name; fields not given are zero."""
    fmt = endian + "".join(code for _, code in fields)
    zero = {name: b"" if code.endswith("s") else 0 for name, code in fields}
    return struct.pack(fmt, *({**zero, **values}[name] for name, _ in fields))


def build_macho(
    segments: Sequence[tuple[str, Sequence[MachOSection]]],
    *,
    is_64: bool = True,
    big_endian: bool = False,
    other_commands: int = 0,
) -> bytes:
    """Build a thin Mach-O file: header, load commands, then section contents.

    Each segment is a (segname, sections) pair. Sections with content get it
    laid out after the load commands, in order; sections without content get
    offset 0, like zerofill. other_commands prepends that many LC_SYMTAB load
    commands, which a parser must step over.
    """
    e = ">" if big_endian else "<"
    if is_64:
        magic, cmd = MH_MAGIC_64, LC_SEGMENT_64
        header, segment, section = MACH_HEADER_64, SEGMENT_COMMAND_64, SECTION_64
    else:
        magic, cmd = MH_MAGIC, LC_SEGMENT
        header, segment, section = MACH_HEADER, SEGMENT_COMMAND, SECTION
    symtab = _pack(SYMTAB_COMMAND, e, cmd=LC_SYMTAB, cmdsize=sizeof(SYMTAB_COMMAND))

    commands_size = len(symtab) * other_commands + sum(
        sizeof(segment) + len(sections) * sizeof(section) for _, sections in segments
    )
    contents_start = sizeof(header) + commands_size
    commands = bytearray(symtab * other_commands)
    contents = bytearray()
    for segname, sections in segments:
        commands += _pack(
            segment,
            e,
            cmd=cmd,
            cmdsize=sizeof(segment) + len(sections) * sizeof(section),
            segname=segname.encode(),
            nsects=len(sections),
        )
        for s in sections:
            offset = s.offset
            if offset is None:
                offset = contents_start + len(contents) if s.content else 0
            commands += _pack(
                section,
                e,
                sectname=s.sectname.encode(),
                segname=s.segname.encode(),
                size=len(s.content) if s.size is None else s.size,
                offset=offset,
                flags=s.flags,
            )
            contents += s.content
    ncmds = other_commands + len(segments)
    return (
        _pack(
            header,
            e,
            magic=magic,
            filetype=MH_OBJECT,
            ncmds=ncmds,
            sizeofcmds=len(commands),
        )
        + commands
        + contents
    )


# --- ELF, transcribed from <elf.h> ---
#
# Deliberately independent of sillystrings.formats.elf -- nothing is shared --
# so a field or constant the parser gets wrong cannot be wrong the same way
# here. tests/test_elf_constants.py checks both against the real header.

EI_MAG0 = 0  # elf.h: #define EI_MAG0 0
ELFMAG0 = 0x7F  # elf.h: #define ELFMAG0 0x7f
ELFMAG1 = ord("E")  # elf.h: #define ELFMAG1 'E'
ELFMAG2 = ord("L")  # elf.h: #define ELFMAG2 'L'
ELFMAG3 = ord("F")  # elf.h: #define ELFMAG3 'F'
SELFMAG = 4  # elf.h: #define SELFMAG 4
EI_CLASS = 4  # elf.h: #define EI_CLASS 4
EI_DATA = 5  # elf.h: #define EI_DATA 5
EI_VERSION = 6  # elf.h: #define EI_VERSION 6
ELFCLASSNONE = 0  # elf.h: #define ELFCLASSNONE 0
ELFCLASS32 = 1  # elf.h: #define ELFCLASS32 1
ELFCLASS64 = 2  # elf.h: #define ELFCLASS64 2
ELFDATANONE = 0  # elf.h: #define ELFDATANONE 0
ELFDATA2LSB = 1  # elf.h: #define ELFDATA2LSB 1
ELFDATA2MSB = 2  # elf.h: #define ELFDATA2MSB 2
EV_NONE = 0  # elf.h: #define EV_NONE 0
EV_CURRENT = 1  # elf.h: #define EV_CURRENT 1
ET_NONE = 0  # elf.h: #define ET_NONE 0
ET_REL = 1  # elf.h: #define ET_REL 1
ET_EXEC = 2  # elf.h: #define ET_EXEC 2
ET_DYN = 3  # elf.h: #define ET_DYN 3
ET_CORE = 4  # elf.h: #define ET_CORE 4
ET_LOOS = 0xFE00  # elf.h: #define ET_LOOS 0xfe00
EM_PPC = 20  # elf.h: #define EM_PPC 20
SHN_UNDEF = 0  # elf.h: #define SHN_UNDEF 0
SHN_LORESERVE = 0xFF00  # elf.h: #define SHN_LORESERVE 0xff00
SHN_XINDEX = 0xFFFF  # elf.h: #define SHN_XINDEX 0xffff
SHT_NULL = 0  # elf.h: #define SHT_NULL 0
SHT_PROGBITS = 1  # elf.h: #define SHT_PROGBITS 1
SHT_SYMTAB = 2  # elf.h: #define SHT_SYMTAB 2
SHT_STRTAB = 3  # elf.h: #define SHT_STRTAB 3
SHT_RELA = 4  # elf.h: #define SHT_RELA 4
SHT_HASH = 5  # elf.h: #define SHT_HASH 5
SHT_DYNAMIC = 6  # elf.h: #define SHT_DYNAMIC 6
SHT_NOTE = 7  # elf.h: #define SHT_NOTE 7
SHT_NOBITS = 8  # elf.h: #define SHT_NOBITS 8
SHT_REL = 9  # elf.h: #define SHT_REL 9
SHT_SHLIB = 10  # elf.h: #define SHT_SHLIB 10
SHT_DYNSYM = 11  # elf.h: #define SHT_DYNSYM 11
SHT_INIT_ARRAY = 14  # elf.h: #define SHT_INIT_ARRAY 14
SHT_SYMTAB_SHNDX = 18  # elf.h: #define SHT_SYMTAB_SHNDX 18
SHT_LOOS = 0x60000000  # elf.h: #define SHT_LOOS 0x60000000
SHT_GNU_HASH = 0x6FFFFFF6  # elf.h: #define SHT_GNU_HASH 0x6ffffff6
SHF_WRITE = 1 << 0  # elf.h: #define SHF_WRITE (1 << 0)
SHF_ALLOC = 1 << 1  # elf.h: #define SHF_ALLOC (1 << 1)
SHF_EXECINSTR = 1 << 2  # elf.h: #define SHF_EXECINSTR (1 << 2)
SHF_INFO_LINK = 1 << 6  # elf.h: #define SHF_INFO_LINK (1 << 6)
SHF_COMPRESSED = 1 << 11  # elf.h: #define SHF_COMPRESSED (1 << 11)

# Each struct as (field name, struct format code), in header order:
# B = unsigned char, H = uint16_t (Elf32_Half, Elf64_Half), I = uint32_t
# (Elf32_Word, Elf32_Addr, Elf32_Off, Elf64_Word), Q = uint64_t (Elf64_Xword,
# Elf64_Addr, Elf64_Off), q = int64_t (Elf64_Sxword),
# 16s = unsigned char[EI_NIDENT]
ELF32_EHDR: Fields = [  # Elf32_Ehdr
    ("e_ident", "16s"),  # unsigned char[EI_NIDENT]
    ("e_type", "H"),  # Elf32_Half
    ("e_machine", "H"),  # Elf32_Half
    ("e_version", "I"),  # Elf32_Word
    ("e_entry", "I"),  # Elf32_Addr
    ("e_phoff", "I"),  # Elf32_Off
    ("e_shoff", "I"),  # Elf32_Off
    ("e_flags", "I"),  # Elf32_Word
    ("e_ehsize", "H"),  # Elf32_Half
    ("e_phentsize", "H"),  # Elf32_Half
    ("e_phnum", "H"),  # Elf32_Half
    ("e_shentsize", "H"),  # Elf32_Half
    ("e_shnum", "H"),  # Elf32_Half
    ("e_shstrndx", "H"),  # Elf32_Half
]
ELF64_EHDR: Fields = [  # Elf64_Ehdr
    ("e_ident", "16s"),  # unsigned char[EI_NIDENT]
    ("e_type", "H"),  # Elf64_Half
    ("e_machine", "H"),  # Elf64_Half
    ("e_version", "I"),  # Elf64_Word
    ("e_entry", "Q"),  # Elf64_Addr
    ("e_phoff", "Q"),  # Elf64_Off
    ("e_shoff", "Q"),  # Elf64_Off
    ("e_flags", "I"),  # Elf64_Word
    ("e_ehsize", "H"),  # Elf64_Half
    ("e_phentsize", "H"),  # Elf64_Half
    ("e_phnum", "H"),  # Elf64_Half
    ("e_shentsize", "H"),  # Elf64_Half
    ("e_shnum", "H"),  # Elf64_Half
    ("e_shstrndx", "H"),  # Elf64_Half
]
ELF32_SHDR: Fields = [  # Elf32_Shdr
    ("sh_name", "I"),  # Elf32_Word
    ("sh_type", "I"),  # Elf32_Word
    ("sh_flags", "I"),  # Elf32_Word
    ("sh_addr", "I"),  # Elf32_Addr
    ("sh_offset", "I"),  # Elf32_Off
    ("sh_size", "I"),  # Elf32_Word
    ("sh_link", "I"),  # Elf32_Word
    ("sh_info", "I"),  # Elf32_Word
    ("sh_addralign", "I"),  # Elf32_Word
    ("sh_entsize", "I"),  # Elf32_Word
]
ELF64_SHDR: Fields = [  # Elf64_Shdr
    ("sh_name", "I"),  # Elf64_Word
    ("sh_type", "I"),  # Elf64_Word
    ("sh_flags", "Q"),  # Elf64_Xword
    ("sh_addr", "Q"),  # Elf64_Addr
    ("sh_offset", "Q"),  # Elf64_Off
    ("sh_size", "Q"),  # Elf64_Xword
    ("sh_link", "I"),  # Elf64_Word
    ("sh_info", "I"),  # Elf64_Word
    ("sh_addralign", "Q"),  # Elf64_Xword
    ("sh_entsize", "Q"),  # Elf64_Xword
]
# The table entries tests give their sections, for sh_entsize
ELF64_SYM: Fields = [  # Elf64_Sym
    ("st_name", "I"),  # Elf64_Word
    ("st_info", "B"),  # unsigned char
    ("st_other", "B"),  # unsigned char
    ("st_shndx", "H"),  # Elf64_Section (uint16_t)
    ("st_value", "Q"),  # Elf64_Addr
    ("st_size", "Q"),  # Elf64_Xword
]
ELF64_REL: Fields = [  # Elf64_Rel
    ("r_offset", "Q"),  # Elf64_Addr
    ("r_info", "Q"),  # Elf64_Xword
]
ELF64_RELA: Fields = [  # Elf64_Rela
    ("r_offset", "Q"),  # Elf64_Addr
    ("r_info", "Q"),  # Elf64_Xword
    ("r_addend", "q"),  # Elf64_Sxword
]


@dataclass(frozen=True)
class ElfSection:
    name: str
    content: bytes = b""
    type: int = SHT_PROGBITS
    flags: int = 0
    link: int = 0
    info: int = 0
    entsize: int = 0
    # Override the header fields, which otherwise describe content as placed
    size: int | None = None
    offset: int | None = None
    name_offset: int | None = None


def build_elf(
    sections: Sequence[ElfSection],
    *,
    is_64: bool = True,
    big_endian: bool = False,
    e_type: int = ET_REL,
    extended: bool = False,
) -> bytes:
    """Build an ELF file: header, section contents, names, then the headers.

    The section header table is the null section, the given sections in order,
    then .shstrtab, so the given sections have indexes 1 to len(sections).
    extended stores the section count and string table index in section 0, as
    files with SHN_LORESERVE or more sections must.
    """
    e = ">" if big_endian else "<"
    ehdr, shdr = (ELF64_EHDR, ELF64_SHDR) if is_64 else (ELF32_EHDR, ELF32_SHDR)
    ident = bytearray(EI_VERSION + 1)
    ident[:EI_CLASS] = bytes([ELFMAG0, ELFMAG1, ELFMAG2, ELFMAG3])
    ident[EI_CLASS] = ELFCLASS64 if is_64 else ELFCLASS32
    ident[EI_DATA] = ELFDATA2MSB if big_endian else ELFDATA2LSB
    ident[EI_VERSION] = EV_CURRENT

    # The name string table goes last among the contents, and names itself
    all_sections = [*sections, ElfSection(".shstrtab", type=SHT_STRTAB)]
    names = bytearray(b"\0")
    name_offsets = []
    for s in all_sections:
        name_offsets.append(len(names))
        names += s.name.encode() + b"\0"
    all_sections[-1] = ElfSection(".shstrtab", bytes(names), type=SHT_STRTAB)

    contents_start = sizeof(ehdr)
    contents = bytearray()
    headers = [b""]  # section 0, filled in once the count is known
    for s, name_offset in zip(all_sections, name_offsets, strict=True):
        offset = contents_start + len(contents) if s.offset is None else s.offset
        contents += s.content
        headers.append(
            _pack(
                shdr,
                e,
                sh_name=name_offset if s.name_offset is None else s.name_offset,
                sh_type=s.type,
                sh_flags=s.flags,
                sh_offset=offset,
                sh_size=len(s.content) if s.size is None else s.size,
                sh_link=s.link,
                sh_info=s.info,
                sh_entsize=s.entsize,
            )
        )
    shnum, shstrndx = len(headers), len(headers) - 1
    headers[0] = _pack(
        shdr,
        e,
        sh_size=shnum if extended else 0,
        sh_link=shstrndx if extended else SHN_UNDEF,
    )
    header = _pack(
        ehdr,
        e,
        e_ident=bytes(ident),
        e_type=e_type,
        e_version=EV_CURRENT,
        e_shoff=contents_start + len(contents),
        e_ehsize=sizeof(ehdr),
        e_shentsize=sizeof(shdr),
        e_shnum=SHN_UNDEF if extended else shnum,
        e_shstrndx=SHN_XINDEX if extended else shstrndx,
    )
    return header + contents + b"".join(headers)


@pytest.fixture(scope="session")
def make_binary_file(
    tmp_path_factory: pytest.TempPathFactory,
) -> Callable[[], Path]:
    tmp_path = tmp_path_factory.mktemp("cli")
    counter = itertools.count()
    data = b"hello" + b"\x00" + b"world" + b"\x00" + b"test string"

    def _make() -> Path:
        p = tmp_path / f"sample_{next(counter)}.bin"
        p.write_bytes(data)
        return p

    return _make
