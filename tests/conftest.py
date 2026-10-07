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


# The structs of <mach-o/loader.h>, field by field, as (name, struct format).
# Written out in full rather than shared with the parser, so a field the parser
# misplaces cannot be misplaced the same way here.
_MACH_HEADER = [
    ("magic", "I"),
    ("cputype", "i"),
    ("cpusubtype", "i"),
    ("filetype", "I"),
    ("ncmds", "I"),
    ("sizeofcmds", "I"),
    ("flags", "I"),
]
_MACH_HEADER_64 = [*_MACH_HEADER, ("reserved", "I")]
_SEGMENT_COMMAND = [
    ("cmd", "I"),
    ("cmdsize", "I"),
    ("segname", "16s"),
    ("vmaddr", "I"),
    ("vmsize", "I"),
    ("fileoff", "I"),
    ("filesize", "I"),
    ("maxprot", "i"),
    ("initprot", "i"),
    ("nsects", "I"),
    ("flags", "I"),
]
_SEGMENT_COMMAND_64 = [
    (name, "Q" if name in {"vmaddr", "vmsize", "fileoff", "filesize"} else fmt)
    for name, fmt in _SEGMENT_COMMAND
]
_SECTION = [
    ("sectname", "16s"),
    ("segname", "16s"),
    ("addr", "I"),
    ("size", "I"),
    ("offset", "I"),
    ("align", "I"),
    ("reloff", "I"),
    ("nreloc", "I"),
    ("flags", "I"),
    ("reserved1", "I"),
    ("reserved2", "I"),
]
_SECTION_64 = [
    *[(name, "Q" if name in {"addr", "size"} else fmt) for name, fmt in _SECTION],
    ("reserved3", "I"),
]
_SYMTAB_COMMAND = [
    ("cmd", "I"),
    ("cmdsize", "I"),
    ("symoff", "I"),
    ("nsyms", "I"),
    ("stroff", "I"),
    ("strsize", "I"),
]


def _pack(fields: list[tuple[str, str]], endian: str, **values: int | bytes) -> bytes:
    """Pack a struct by field name; fields not given are zero."""
    fmt = endian + "".join(f for _, f in fields)
    zero = {name: b"" if f.endswith("s") else 0 for name, f in fields}
    return struct.pack(fmt, *({**zero, **values}[name] for name, _ in fields))


def _size(fields: list[tuple[str, str]]) -> int:
    return struct.calcsize("=" + "".join(f for _, f in fields))


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
        magic, cmd = 0xFEEDFACF, 0x19  # MH_MAGIC_64, LC_SEGMENT_64
        header, segment, section = _MACH_HEADER_64, _SEGMENT_COMMAND_64, _SECTION_64
    else:
        magic, cmd = 0xFEEDFACE, 0x1  # MH_MAGIC, LC_SEGMENT
        header, segment, section = _MACH_HEADER, _SEGMENT_COMMAND, _SECTION
    symtab = _pack(_SYMTAB_COMMAND, e, cmd=0x2, cmdsize=_size(_SYMTAB_COMMAND))

    commands_size = len(symtab) * other_commands + sum(
        _size(segment) + len(sections) * _size(section) for _, sections in segments
    )
    contents_start = _size(header) + commands_size
    commands = bytearray(symtab * other_commands)
    contents = bytearray()
    for segname, sections in segments:
        commands += _pack(
            segment,
            e,
            cmd=cmd,
            cmdsize=_size(segment) + len(sections) * _size(section),
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
        _pack(header, e, magic=magic, ncmds=ncmds, sizeofcmds=len(commands))
        + commands
        + contents
    )


@dataclass(frozen=True)
class ElfSection:
    name: str
    content: bytes = b""
    type: int = 1  # SHT_PROGBITS
    flags: int = 0
    link: int = 0
    info: int = 0
    entsize: int = 0
    # Override the header fields, which otherwise describe content as placed
    size: int | None = None
    offset: int | None = None
    name_offset: int | None = None


# The structs of <elf.h>, field by field, as (name, struct format). As with the
# Mach-O structs above, nothing here is shared with the parser.
_ELF32_EHDR = [
    ("e_ident", "16s"),
    ("e_type", "H"),
    ("e_machine", "H"),
    ("e_version", "I"),
    ("e_entry", "I"),
    ("e_phoff", "I"),
    ("e_shoff", "I"),
    ("e_flags", "I"),
    ("e_ehsize", "H"),
    ("e_phentsize", "H"),
    ("e_phnum", "H"),
    ("e_shentsize", "H"),
    ("e_shnum", "H"),
    ("e_shstrndx", "H"),
]
_ELF64_EHDR = [
    (name, "Q" if name in {"e_entry", "e_phoff", "e_shoff"} else fmt)
    for name, fmt in _ELF32_EHDR
]
_ELF32_SHDR = [
    ("sh_name", "I"),
    ("sh_type", "I"),
    ("sh_flags", "I"),
    ("sh_addr", "I"),
    ("sh_offset", "I"),
    ("sh_size", "I"),
    ("sh_link", "I"),
    ("sh_info", "I"),
    ("sh_addralign", "I"),
    ("sh_entsize", "I"),
]
_ELF64_SHDR = [
    (
        name,
        "I" if name in {"sh_name", "sh_type", "sh_link", "sh_info"} else "Q",
    )
    for name, _ in _ELF32_SHDR
]


def build_elf(
    sections: Sequence[ElfSection],
    *,
    is_64: bool = True,
    big_endian: bool = False,
    e_type: int = 1,  # ET_REL
    extended: bool = False,
) -> bytes:
    """Build an ELF file: header, section contents, names, then the headers.

    The section header table is the null section, the given sections in order,
    then .shstrtab, so the given sections have indexes 1 to len(sections).
    extended stores the section count and string table index in section 0, as
    files with SHN_LORESERVE or more sections must.
    """
    e = ">" if big_endian else "<"
    ehdr, shdr = (_ELF64_EHDR, _ELF64_SHDR) if is_64 else (_ELF32_EHDR, _ELF32_SHDR)
    # EI_MAG0-3, EI_CLASS (ELFCLASS32/64), EI_DATA (ELFDATA2LSB/MSB), EI_VERSION
    ident = b"\x7fELF" + bytes([2 if is_64 else 1, 2 if big_endian else 1, 1])

    # The name string table goes last among the contents, and names itself
    all_sections = [*sections, ElfSection(".shstrtab", type=3)]  # SHT_STRTAB
    names = bytearray(b"\0")
    name_offsets = []
    for s in all_sections:
        name_offsets.append(len(names))
        names += s.name.encode() + b"\0"
    all_sections[-1] = ElfSection(".shstrtab", bytes(names), type=3)

    contents_start = _size(ehdr)
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
        shdr, e, sh_size=shnum if extended else 0, sh_link=shstrndx if extended else 0
    )
    header = _pack(
        ehdr,
        e,
        e_ident=ident,
        e_type=e_type,
        e_version=1,  # EV_CURRENT
        e_shoff=contents_start + len(contents),
        e_ehsize=_size(ehdr),
        e_shentsize=_size(shdr),
        e_shnum=0 if extended else shnum,  # SHN_UNDEF
        e_shstrndx=0xFFFF if extended else shstrndx,  # SHN_XINDEX
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
