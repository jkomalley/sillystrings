from sillystrings.formats import data_ranges

from .conftest import (
    S_ZEROFILL,
    SHF_ALLOC,
    SHF_EXECINSTR,
    ElfSection,
    MachOSection,
    build_elf,
    build_macho,
)


class TestDataRanges:
    def test_macho_sections_as_file_offsets(self) -> None:
        data = build_macho(
            [
                ("__TEXT", [MachOSection("__TEXT", "__text", b"code")]),
                ("__DATA", [MachOSection("__DATA", "__data", b"hello")]),
            ]
        )
        assert data_ranges(data) == [
            (data.index(b"code"), 4),
            (data.index(b"hello"), 5),
        ]

    def test_elf_sections_as_file_offsets(self) -> None:
        data = build_elf(
            [
                ElfSection(".text", b"code", flags=SHF_ALLOC | SHF_EXECINSTR),
                ElfSection(".comment", b"GCC: 1"),
                ElfSection(".rodata", b"hello", flags=SHF_ALLOC),
            ]
        )
        assert data_ranges(data) == [
            (data.index(b"code"), 4),
            (data.index(b"hello"), 5),
        ]

    def test_elf_with_no_data_sections_is_none(self) -> None:
        # Such as an object built from an empty source file
        assert data_ranges(build_elf([ElfSection(".comment", b"GCC: 1")])) is None

    def test_unrecognized_is_none(self) -> None:
        assert data_ranges(b"\x00hello world\x00") is None

    def test_damaged_structure_is_none(self) -> None:
        data = build_macho([("", [MachOSection("__DATA", "__data", b"hello")])])
        assert data_ranges(data[:40]) is None

    def test_only_sections_outside_the_file_is_none(self) -> None:
        data = build_macho([("", [MachOSection("__DATA", "__data", b"hello")])])
        assert data_ranges(data[:-1]) is None

    def test_no_data_sections_is_none(self) -> None:
        # GNU strings scans the whole file when -d found no section to scan
        bss = MachOSection("__DATA", "__bss", size=64, flags=S_ZEROFILL)
        assert data_ranges(build_macho([("__DATA", [bss])])) is None
        assert data_ranges(build_macho([])) is None
