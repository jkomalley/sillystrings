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
