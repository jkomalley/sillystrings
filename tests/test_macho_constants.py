"""Check the Mach-O definitions against the real <mach-o/loader.h>.

The parser (sillystrings.formats.macho) and the test builder (conftest) each
transcribe loader.h's structs and constants by hand, independently. This test
generates a C program from both transcriptions, compiles it against the system
header, and checks every field's offset, size and signedness, every struct's
size, and every constant's value. A field name that the header lacks fails the
compile.

It needs a C compiler and the macOS SDK headers, so it is skipped elsewhere
(CI runs on Ubuntu).
"""

import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from typing import get_type_hints

import pytest

from sillystrings.formats import macho

from . import conftest
from .test_macho import CPU_TYPE_POWERPC, FAT_MAGIC, FAT_MAGIC_64

HEADERS = ("mach-o/loader.h", "mach-o/fat.h", "mach/machine.h")


def _have_headers() -> bool:
    cc = shutil.which("cc")
    if cc is None:
        return False
    probe = "".join(f"#include <{h}>\n" for h in HEADERS) + "int main(void){}\n"
    result = subprocess.run(
        [cc, "-x", "c", "-fsyntax-only", "-"],
        input=probe.encode(),
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


pytestmark = pytest.mark.skipif(
    not _have_headers(), reason="needs cc and the macOS <mach-o/loader.h>"
)

Fields = list[tuple[str, str]]


def _namedtuple_fields(cls: type[tuple]) -> Fields:
    hints = get_type_hints(cls, include_extras=True)
    return [(name, hint.__metadata__[0]) for name, hint in hints.items()]


# C struct name -> (field name, struct format code), from each transcription
PARSER_STRUCTS: dict[str, Fields] = {
    "mach_header": _namedtuple_fields(macho.MachHeader),
    "mach_header_64": _namedtuple_fields(macho.MachHeader64),
    "load_command": _namedtuple_fields(macho.LoadCommand),
    "segment_command": _namedtuple_fields(macho.SegmentCommand),
    "segment_command_64": _namedtuple_fields(macho.SegmentCommand64),
    "section": _namedtuple_fields(macho.Section32),
    "section_64": _namedtuple_fields(macho.Section64),
}
BUILDER_STRUCTS: dict[str, Fields] = {
    "mach_header": conftest.MACH_HEADER,
    "mach_header_64": conftest.MACH_HEADER_64,
    "segment_command": conftest.SEGMENT_COMMAND,
    "segment_command_64": conftest.SEGMENT_COMMAND_64,
    "section": conftest.SECTION,
    "section_64": conftest.SECTION_64,
    "symtab_command": conftest.SYMTAB_COMMAND,
}

# C macro name -> the value a transcription gives it
PARSER_CONSTANTS = {
    name: getattr(macho, name)
    for name in (
        "MH_MAGIC",
        "MH_CIGAM",
        "MH_MAGIC_64",
        "MH_CIGAM_64",
        "LC_SEGMENT",
        "LC_SEGMENT_64",
        "SECTION_TYPE",
        "S_ZEROFILL",
        "S_ATTR_DEBUG",
    )
}
BUILDER_CONSTANTS = {
    name: getattr(conftest, name)
    for name in (
        "MH_MAGIC",
        "MH_MAGIC_64",
        "MH_OBJECT",
        "LC_SEGMENT",
        "LC_SYMTAB",
        "LC_SEGMENT_64",
        "S_ZEROFILL",
        "S_GB_ZEROFILL",
        "S_THREAD_LOCAL_ZEROFILL",
        "S_ATTR_PURE_INSTRUCTIONS",
        "S_ATTR_DEBUG",
    )
}
TEST_CONSTANTS = {
    "CPU_TYPE_POWERPC": CPU_TYPE_POWERPC,
    "FAT_MAGIC": FAT_MAGIC,
    "FAT_MAGIC_64": FAT_MAGIC_64,
}


@dataclass
class Header:
    """What the compiled program reports about the real header."""

    sizes: dict[str, int] = field(default_factory=dict)
    # (struct, field) -> (offset, size, signed), where signed is -1 for arrays
    fields: dict[tuple[str, str], tuple[int, int, int]] = field(default_factory=dict)
    constants: dict[str, int] = field(default_factory=dict)


def _c_program() -> str:
    lines = [f"#include <{h}>" for h in HEADERS]
    lines += ["#include <stddef.h>", "#include <stdio.h>", "int main(void) {"]
    structs = {**PARSER_STRUCTS, **BUILDER_STRUCTS}
    for name in structs:
        lines.append(f'printf("sizeof {name} %zu\\n", sizeof(struct {name}));')
    for name, fields in [*PARSER_STRUCTS.items(), *BUILDER_STRUCTS.items()]:
        for member, code in fields:
            ref = f"((struct {name} *)0)->{member}"
            signed = "-1" if code.endswith("s") else f"((__typeof__({ref}))-1 < 0)"
            lines.append(
                f'printf("field {name} {member} %zu %zu %d\\n",'
                f" offsetof(struct {name}, {member}), sizeof({ref}), (int){signed});"
            )
    for name in {**PARSER_CONSTANTS, **BUILDER_CONSTANTS, **TEST_CONSTANTS}:
        lines.append(f'printf("const {name} %llu\\n", (unsigned long long)({name}));')
    lines += ["return 0;", "}"]
    return "\n".join(lines) + "\n"


@pytest.fixture(scope="module")
def header(tmp_path_factory: pytest.TempPathFactory) -> Header:
    cc = shutil.which("cc")
    assert cc is not None
    exe = tmp_path_factory.mktemp("loader_h") / "dump"
    compiled = subprocess.run(
        [cc, "-x", "c", "-", "-o", str(exe)],
        input=_c_program().encode(),
        capture_output=True,
        check=False,
    )
    # A transcribed field name the header doesn't have fails here
    assert compiled.returncode == 0, compiled.stderr.decode()
    output = subprocess.run([str(exe)], capture_output=True, check=True, text=True)

    result = Header()
    for line in output.stdout.splitlines():
        kind, *rest = line.split()
        if kind == "sizeof":
            result.sizes[rest[0]] = int(rest[1])
        elif kind == "field":
            offset, size, signed = map(int, rest[2:])
            result.fields[rest[0], rest[1]] = (offset, size, signed)
        else:
            result.constants[rest[0]] = int(rest[1])
    return result


def _layout(fields: Fields) -> list[tuple[str, int, int, int]]:
    """Each field's (name, offset, size, signed), as the struct module packs it."""
    result = []
    offset = 0
    for name, code in fields:
        # Standard sizes, no padding: "<" rather than native "@"
        size = struct.calcsize("<" + code)
        signed = -1 if code.endswith("s") else int(code.islower())
        result.append((name, offset, size, signed))
        offset += size
    return result


@pytest.mark.parametrize(
    ("name", "fields"),
    [
        *[pytest.param(n, f, id=f"parser-{n}") for n, f in PARSER_STRUCTS.items()],
        *[pytest.param(n, f, id=f"builder-{n}") for n, f in BUILDER_STRUCTS.items()],
    ],
)
def test_struct_matches_header(header: Header, name: str, fields: Fields) -> None:
    expected = [(member, *header.fields[name, member]) for member, _ in fields]
    assert _layout(fields) == expected
    # With every offset and size matching, an equal total leaves no room for a
    # field the transcription missed
    assert sum(size for _, _, size, _ in _layout(fields)) == header.sizes[name]


@pytest.mark.parametrize(
    ("name", "value"),
    [
        *[pytest.param(n, v, id=f"parser-{n}") for n, v in PARSER_CONSTANTS.items()],
        *[pytest.param(n, v, id=f"builder-{n}") for n, v in BUILDER_CONSTANTS.items()],
        *[pytest.param(n, v, id=f"test-{n}") for n, v in TEST_CONSTANTS.items()],
    ],
)
def test_constant_matches_header(header: Header, name: str, value: int) -> None:
    assert value == header.constants[name]


def test_dwarf_names_fit_a_section_name() -> None:
    # sectname is char[16], so BFD's table holds names cut to 16 characters
    assert all(len(name) <= 16 for name in macho.BFD_DWARF_SECTIONS)
