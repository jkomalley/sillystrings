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
