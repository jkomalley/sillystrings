"""Check the ELF definitions against the real <elf.h>.

The parser (sillystrings.formats.elf) and the test builder (conftest) each
transcribe elf.h's structs and constants by hand, independently. This test
generates a C program from both transcriptions, compiles it against the system
header, and checks every field's offset, size and signedness, every struct's
size, and every constant's value. A field name that the header lacks fails the
compile.

It needs a C compiler and glibc's <elf.h>, so it runs on Linux, CI's Ubuntu
included, and is skipped on macOS, which has no <elf.h>.
"""

import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from typing import get_type_hints

import pytest

from sillystrings.formats import elf

from . import conftest

HEADERS = ("elf.h",)


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


pytestmark = pytest.mark.skipif(not _have_headers(), reason="needs cc and <elf.h>")

Fields = list[tuple[str, str]]


def _namedtuple_fields(cls: type[tuple]) -> Fields:
    hints = get_type_hints(cls, include_extras=True)
    return [(name, hint.__metadata__[0]) for name, hint in hints.items()]


# C typedef name -> (field name, struct format code), from each transcription
PARSER_STRUCTS: dict[str, Fields] = {
    "Elf32_Ehdr": _namedtuple_fields(elf.Elf32_Ehdr),
    "Elf64_Ehdr": _namedtuple_fields(elf.Elf64_Ehdr),
    "Elf32_Shdr": _namedtuple_fields(elf.Elf32_Shdr),
    "Elf64_Shdr": _namedtuple_fields(elf.Elf64_Shdr),
}
BUILDER_STRUCTS: dict[str, Fields] = {
    "Elf32_Ehdr": conftest.ELF32_EHDR,
    "Elf64_Ehdr": conftest.ELF64_EHDR,
    "Elf32_Shdr": conftest.ELF32_SHDR,
    "Elf64_Shdr": conftest.ELF64_SHDR,
    "Elf64_Sym": conftest.ELF64_SYM,
    "Elf64_Rel": conftest.ELF64_REL,
    "Elf64_Rela": conftest.ELF64_RELA,
}

# C macro name -> the value a transcription gives it
PARSER_CONSTANTS = {
    name: getattr(elf, name)
    for name in (
        "EI_NIDENT",
        "ELFMAG0",
        "ELFMAG1",
        "ELFMAG2",
        "ELFMAG3",
        "SELFMAG",
        "EI_CLASS",
        "ELFCLASS32",
        "ELFCLASS64",
        "EI_DATA",
        "ELFDATA2LSB",
        "ELFDATA2MSB",
        "EI_VERSION",
        "EV_CURRENT",
        "ET_EXEC",
        "ET_DYN",
        "ET_CORE",
        "SHN_UNDEF",
        "SHN_LORESERVE",
        "SHN_XINDEX",
        "SHT_NULL",
        "SHT_SYMTAB",
        "SHT_STRTAB",
        "SHT_RELA",
        "SHT_NOTE",
        "SHT_NOBITS",
        "SHT_REL",
        "SHT_SHLIB",
        "SHT_SYMTAB_SHNDX",
        "SHF_ALLOC",
        "SHF_COMPRESSED",
    )
}
BUILDER_CONSTANTS = {
    name: getattr(conftest, name)
    for name in (
        "EI_MAG0",
        "ELFMAG0",
        "ELFMAG1",
        "ELFMAG2",
        "ELFMAG3",
        "SELFMAG",
        "EI_CLASS",
        "EI_DATA",
        "EI_VERSION",
        "ELFCLASSNONE",
        "ELFCLASS32",
        "ELFCLASS64",
        "ELFDATANONE",
        "ELFDATA2LSB",
        "ELFDATA2MSB",
        "EV_NONE",
        "EV_CURRENT",
        "ET_NONE",
        "ET_REL",
        "ET_EXEC",
        "ET_DYN",
        "ET_CORE",
        "ET_LOOS",
        "EM_PPC",
        "SHN_UNDEF",
        "SHN_LORESERVE",
        "SHN_XINDEX",
        "SHT_NULL",
        "SHT_PROGBITS",
        "SHT_SYMTAB",
        "SHT_STRTAB",
        "SHT_RELA",
        "SHT_HASH",
        "SHT_DYNAMIC",
        "SHT_NOTE",
        "SHT_NOBITS",
        "SHT_REL",
        "SHT_SHLIB",
        "SHT_DYNSYM",
        "SHT_INIT_ARRAY",
        "SHT_SYMTAB_SHNDX",
        "SHT_LOOS",
        "SHT_GNU_HASH",
        "SHF_WRITE",
        "SHF_ALLOC",
        "SHF_EXECINSTR",
        "SHF_INFO_LINK",
        "SHF_COMPRESSED",
    )
}


@dataclass
class Header:
    """What the compiled program reports about the real header."""

    sizes: dict[str, int] = field(default_factory=dict)
    # (struct, field) -> (offset, size, signed), where signed is -1 for arrays
    fields: dict[tuple[str, str], tuple[int, int, int]] = field(default_factory=dict)
    constants: dict[str, int] = field(default_factory=dict)
    magic: bytes = b""


def _c_program() -> str:
    lines = [f"#include <{h}>" for h in HEADERS]
    lines += ["#include <stddef.h>", "#include <stdio.h>", "int main(void) {"]
    structs = {**PARSER_STRUCTS, **BUILDER_STRUCTS}
    for name in structs:
        lines.append(f'printf("sizeof {name} %zu\\n", sizeof({name}));')
    for name, fields in [*PARSER_STRUCTS.items(), *BUILDER_STRUCTS.items()]:
        for member, code in fields:
            ref = f"(({name} *)0)->{member}"
            signed = "-1" if code.endswith("s") else f"((__typeof__({ref}))-1 < 0)"
            lines.append(
                f'printf("field {name} {member} %zu %zu %d\\n",'
                f" offsetof({name}, {member}), sizeof({ref}), (int){signed});"
            )
    for name in {**PARSER_CONSTANTS, **BUILDER_CONSTANTS}:
        lines.append(f'printf("const {name} %llu\\n", (unsigned long long)({name}));')
    # ELFMAG is a string, so print its bytes
    lines += [
        'printf("magic ");',
        "for (int i = 0; i < SELFMAG; i++)",
        '    printf("%02x", (unsigned char)ELFMAG[i]);',
        'printf("\\n");',
        "return 0;",
        "}",
    ]
    return "\n".join(lines) + "\n"


@pytest.fixture(scope="module")
def header(tmp_path_factory: pytest.TempPathFactory) -> Header:
    cc = shutil.which("cc")
    assert cc is not None
    exe = tmp_path_factory.mktemp("elf_h") / "dump"
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
        elif kind == "const":
            result.constants[rest[0]] = int(rest[1])
        else:
            result.magic = bytes.fromhex(rest[0])
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
    ],
)
def test_constant_matches_header(header: Header, name: str, value: int) -> None:
    assert value == header.constants[name]


def test_magic_matches_header(header: Header) -> None:
    assert header.magic == elf.ELFMAG
