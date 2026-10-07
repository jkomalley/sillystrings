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
    offset 0, like zerofill. other_commands prepends that many non-segment
    load commands, which a parser must step over. Fields the parser does not
    read are zeroed by the pad bytes ("x") in the formats.
    """
    e = ">" if big_endian else "<"
    if is_64:
        magic, cmd = 0xFEEDFACF, 0x19  # LC_SEGMENT_64
        # magic, cputype..filetype, ncmds, sizeofcmds, flags + reserved
        header = struct.Struct(f"{e}I12xII8x")
        # cmd, cmdsize, segname, vmaddr..filesize, maxprot, initprot, nsects, flags
        segment = struct.Struct(f"{e}II16s32x8xI4x")
        # sectname, segname, addr, size, offset, align..nreloc, flags, reserved1-3
        section = struct.Struct(f"{e}16s16s8xQI12xI12x")
    else:
        magic, cmd = 0xFEEDFACE, 0x1  # LC_SEGMENT
        header = struct.Struct(f"{e}I12xII4x")
        segment = struct.Struct(f"{e}II16s16x8xI4x")
        section = struct.Struct(f"{e}16s16s4xII12xI8x")
    symtab = struct.pack(f"{e}II16x", 0x2, 24)  # LC_SYMTAB, its body zeroed

    commands_size = len(symtab) * other_commands + sum(
        segment.size + len(sections) * section.size for _, sections in segments
    )
    contents_start = header.size + commands_size
    commands = bytearray(symtab * other_commands)
    contents = bytearray()
    for segname, sections in segments:
        cmdsize = segment.size + len(sections) * section.size
        commands += segment.pack(cmd, cmdsize, segname.encode(), len(sections))
        for s in sections:
            offset = s.offset
            if offset is None:
                offset = contents_start + len(contents) if s.content else 0
            size = len(s.content) if s.size is None else s.size
            names = (s.sectname.encode(), s.segname.encode())
            commands += section.pack(*names, size, offset, s.flags)
            contents += s.content
    ncmds = other_commands + len(segments)
    return header.pack(magic, ncmds, len(commands)) + commands + contents


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
