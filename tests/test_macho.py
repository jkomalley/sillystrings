import struct

import pytest

from sillystrings.formats.common import Section
from sillystrings.formats.macho import data_sections

from .conftest import (
    LC_SEGMENT,
    MACH_HEADER_64,
    MH_MAGIC,
    MH_OBJECT,
    S_ATTR_DEBUG,
    S_ATTR_PURE_INSTRUCTIONS,
    S_GB_ZEROFILL,
    S_THREAD_LOCAL_ZEROFILL,
    S_ZEROFILL,
    SECTION_64,
    SEGMENT_COMMAND_64,
    MachOSection,
    build_macho,
    offsetof,
    sizeof,
)

# Every word size and byte order, as (is_64, big_endian)
VARIANTS = [(True, False), (True, True), (False, False), (False, True)]


def sections_of(*sections: MachOSection, **kwargs: bool) -> list[Section] | None:
    """Parse a file whose sections all sit in one segment."""
    return data_sections(build_macho([("", sections)], **kwargs))


def names(result: list[Section] | None) -> list[str]:
    assert result is not None
    return [section.name for section in result]


class TestDataSections:
    @pytest.mark.parametrize(("is_64", "big_endian"), VARIANTS)
    def test_reads_every_variant(self, is_64: bool, big_endian: bool) -> None:
        data = build_macho(
            [
                ("__TEXT", [MachOSection("__TEXT", "__cstring", b"hello\0")]),
                ("__DATA", [MachOSection("__DATA", "__data", b"\0world\0")]),
            ],
            is_64=is_64,
            big_endian=big_endian,
        )
        assert data_sections(data) == [
            Section("__TEXT,__cstring", data.index(b"hello"), 6),
            Section("__DATA,__data", data.index(b"\0world"), 7),
        ]

    def test_code_is_scanned(self) -> None:
        # GNU -d scans every loaded section, code included; this is the rule
        # where it parts ways with macOS strings
        text = MachOSection(
            "__TEXT", "__text", b"\x1f\x20\x03\xd5", flags=S_ATTR_PURE_INSTRUCTIONS
        )
        assert names(sections_of(text)) == ["__TEXT,__text"]

    def test_keeps_load_command_order(self) -> None:
        data = build_macho(
            [
                ("__DATA", [MachOSection("__DATA", "__data", b"d")]),
                ("__TEXT", [MachOSection("__TEXT", "__cstring", b"c")]),
            ]
        )
        assert names(data_sections(data)) == ["__DATA,__data", "__TEXT,__cstring"]

    def test_names_come_from_the_section_not_its_segment(self) -> None:
        # In an MH_OBJECT (.o) file, every section sits in one unnamed segment
        data = build_macho([("", [MachOSection("__TEXT", "__cstring", b"hello")])])
        assert names(data_sections(data)) == ["__TEXT,__cstring"]

    def test_sixteen_character_names_have_no_terminator(self) -> None:
        section = MachOSection("__DATA_CONST1234", "__objc_methlist_", b"x")
        assert names(sections_of(section)) == ["__DATA_CONST1234,__objc_methlist_"]

    def test_steps_over_other_load_commands(self) -> None:
        data = build_macho(
            [("__TEXT", [MachOSection("__TEXT", "__cstring", b"hello")])],
            other_commands=3,
        )
        assert names(data_sections(data)) == ["__TEXT,__cstring"]

    def test_no_segments_is_an_empty_list(self) -> None:
        assert data_sections(build_macho([])) == []

    # (section, scanned)
    @pytest.mark.parametrize(
        ("section", "scanned"),
        [
            # Zerofill sections occupy memory but not the file, so have offset 0
            (MachOSection("__DATA", "__bss", size=64, flags=S_ZEROFILL), False),
            (MachOSection("__DATA", "__huge", size=64, flags=S_GB_ZEROFILL), False),
            (
                MachOSection(
                    "__DATA", "__thread_bss", size=64, flags=S_THREAD_LOCAL_ZEROFILL
                ),
                False,
            ),
            # BFD never loads S_ZEROFILL, whatever its offset...
            (MachOSection("__DATA", "__bss", b"data", flags=S_ZEROFILL), False),
            # ...but loads the other zerofill types, so only offset 0 skips them
            (MachOSection("__DATA", "__huge", b"data", flags=S_GB_ZEROFILL), True),
            # A dSYM keeps the size of sections it holds no bytes of
            (MachOSection("__TEXT", "__text", size=52, offset=0), False),
            (MachOSection("__TEXT", "__cstring", b"", offset=0x100), False),
            (MachOSection("__LD", "__compact_unwind", b"data", S_ATTR_DEBUG), False),
            # BFD knows these DWARF sections by name; a dSYM's have no flags
            (MachOSection("__DWARF", "__debug_info", b"data"), False),
            (MachOSection("__DWARF", "__debug_str", b"data"), False),
            (MachOSection("__DWARF", "__debug_gdb_scri", b"data"), False),
            # Newer DWARF that BFD's name table lacks is loaded, and GNU scans it
            (MachOSection("__DWARF", "__debug_str_offs", b"data"), True),
            (MachOSection("__DWARF", "__debug_str_offs", b"data", S_ATTR_DEBUG), False),
            # The name only counts in the __DWARF segment
            (MachOSection("__DATA", "__debug_info", b"data"), True),
        ],
    )
    def test_which_sections_are_scanned(
        self, section: MachOSection, scanned: bool
    ) -> None:
        data = build_macho(
            [("", [section, MachOSection("__DATA", "__data", b"marker")])]
        )
        expected = ["__DATA,__data"]
        if scanned:
            expected.insert(0, f"{section.segname},{section.sectname}")
        assert names(data_sections(data)) == expected

    def test_accepts_memoryview(self) -> None:
        data = build_macho([("", [MachOSection("__TEXT", "__cstring", b"hello")])])
        with memoryview(data) as view:
            assert data_sections(view) == data_sections(data)


CPU_TYPE_POWERPC = 18  # mach/machine.h: #define CPU_TYPE_POWERPC ((cpu_type_t) 18)
FAT_MAGIC = 0xCAFEBABE  # mach-o/fat.h: #define FAT_MAGIC 0xcafebabe
FAT_MAGIC_64 = 0xCAFEBABF  # mach-o/fat.h: #define FAT_MAGIC_64 0xcafebabf


def test_hand_assembled_big_endian_32_bit_object() -> None:
    # Byte by byte at offsets read off <mach-o/loader.h>, sharing nothing with
    # build_macho or the parser: a PowerPC MH_OBJECT with one LC_SEGMENT
    # holding (__TEXT,__cstring). GNU objdump reads these bytes the same way.
    data = bytearray(162)
    put = struct.pack_into
    # struct mach_header at 0 (28 bytes: seven 4-byte fields)
    put(">I", data, 0, MH_MAGIC)  # magic
    put(">i", data, 4, CPU_TYPE_POWERPC)  # cputype
    put(">I", data, 12, MH_OBJECT)  # filetype
    put(">I", data, 16, 1)  # ncmds
    put(">I", data, 20, 56 + 68)  # sizeofcmds: one segment, one section
    # struct segment_command at 28 (56 bytes)
    put(">I", data, 28 + 0, LC_SEGMENT)  # cmd
    put(">I", data, 28 + 4, 56 + 68)  # cmdsize
    put(">I", data, 28 + 48, 1)  # nsects, after cmd..cmdsize (8),
    # segname (16), vmaddr..filesize (16) and maxprot..initprot (8)
    # struct section at 28 + 56 = 84 (68 bytes)
    put("16s", data, 84 + 0, b"__cstring")  # sectname
    put("16s", data, 84 + 16, b"__TEXT")  # segname
    put(">I", data, 84 + 36, 10)  # size, after addr at 32
    put(">I", data, 84 + 40, 152)  # offset: the bytes after the section
    data[152:162] = b"hello ppc\0"
    assert data_sections(bytes(data)) == [Section("__TEXT,__cstring", 152, 10)]


class TestNotMachO:
    @pytest.mark.parametrize(
        "data",
        [
            b"",
            b"\xcf\xfa\xed",
            b"hello world, this is not a binary",
            b"\x7fELF\x02\x01\x01" + bytes(57),
            b"!<arch>\n" + bytes(60),
            # Fat files are archives to BFD, so GNU -d scans them whole
            struct.pack(">II", FAT_MAGIC, 1) + bytes(20),
            struct.pack(">II", FAT_MAGIC_64, 1) + bytes(32),
            # A Java class file shares the fat magic
            struct.pack(">IHH", FAT_MAGIC, 0, 65) + bytes(16),
        ],
    )
    def test_is_none(self, data: bytes) -> None:
        assert data_sections(data) is None


def _patch(data: bytes, offset: int, value: int) -> bytes:
    patched = bytearray(data)
    struct.pack_into("<I", patched, offset, value)
    return bytes(patched)


# Where the fields these tests corrupt sit in the fixture below: a 64-bit
# header, then one segment command and its first section
SEGMENT = sizeof(MACH_HEADER_64)
SECTION = SEGMENT + sizeof(SEGMENT_COMMAND_64)
NCMDS = offsetof(MACH_HEADER_64, "ncmds")
SIZEOFCMDS = offsetof(MACH_HEADER_64, "sizeofcmds")
CMDSIZE = SEGMENT + offsetof(SEGMENT_COMMAND_64, "cmdsize")
NSECTS = SEGMENT + offsetof(SEGMENT_COMMAND_64, "nsects")
SECTION_SIZE = SECTION + offsetof(SECTION_64, "size")
SECTION_OFFSET = SECTION + offsetof(SECTION_64, "offset")
# The fixture's segment command, with both of its sections
SEGMENT_CMDSIZE = sizeof(SEGMENT_COMMAND_64) + 2 * sizeof(SECTION_64)


class TestMalformed:
    @pytest.fixture
    def data(self) -> bytes:
        return build_macho(
            [
                (
                    "__DATA",
                    [
                        MachOSection("__DATA", "__data", b"hello"),
                        MachOSection("__DATA", "__const", b"world"),
                    ],
                )
            ]
        )

    def test_the_fixture_parses(self, data: bytes) -> None:
        assert names(data_sections(data)) == ["__DATA,__data", "__DATA,__const"]

    def test_every_truncation_of_the_structure(self, data: bytes) -> None:
        # Each prefix cuts into the header or the load commands
        for length in range(data.index(b"hello")):
            assert data_sections(data[:length]) is None, length

    def test_truncated_section_bytes_drop_only_that_section(self, data: bytes) -> None:
        for length in range(data.index(b"world"), len(data)):
            assert names(data_sections(data[:length])) == ["__DATA,__data"], length
        for length in range(data.index(b"hello"), data.index(b"world")):
            assert data_sections(data[:length]) == [], length

    @pytest.mark.parametrize(
        ("offset", "value"),
        [
            (SIZEOFCMDS, 0xFFFFFFFF),  # load commands run past the file
            (NCMDS, 2),  # more commands than sizeofcmds holds
            (NCMDS, 0xFFFFFFFF),
            (CMDSIZE, 0),  # would never advance
            (CMDSIZE, 7),  # smaller than a load_command
            (CMDSIZE, sizeof(SEGMENT_COMMAND_64) - 1),  # cut into the segment
            (CMDSIZE, SEGMENT_CMDSIZE + 8),  # past the end of the load commands
            (NSECTS, 3),  # more sections than the command holds
            (NSECTS, 0xFFFFFFFF),
        ],
    )
    def test_corrupt_field(self, data: bytes, offset: int, value: int) -> None:
        assert data_sections(_patch(data, offset, value)) is None

    @pytest.mark.parametrize(
        ("offset", "value"),
        [
            # The first section's 64-bit size, as when a clang -c object's
            # __const is patched to 0x10000: GNU reports that section unreadable
            # and scans the rest
            (SECTION_SIZE, 0x10000),
            (SECTION_SIZE, 2**64 - 1),
            (SECTION_OFFSET, 0xFFFFFFF0),
        ],
    )
    def test_section_outside_the_file_is_skipped(
        self, data: bytes, offset: int, value: int
    ) -> None:
        patched = bytearray(data)
        fmt = "<Q" if offset == SECTION_SIZE else "<I"
        struct.pack_into(fmt, patched, offset, value)
        assert names(data_sections(bytes(patched))) == ["__DATA,__const"]

    def test_skipped_sections_are_not_bounds_checked(self) -> None:
        # A zerofill section's offset and size describe memory, not the file
        bss = MachOSection("__DATA", "__bss", size=2**40, flags=S_ZEROFILL)
        assert sections_of(bss) == []

    def test_spare_command_space_is_allowed(self, data: bytes) -> None:
        # Linkers leave padding after the load commands for later editing
        assert data_sections(_patch(data, NCMDS, 0)) == []
