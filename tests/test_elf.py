import struct

import pytest

from sillystrings.formats.common import Section
from sillystrings.formats.elf import NAME_LIMIT, data_sections

from .conftest import (
    EI_CLASS,
    EI_DATA,
    EI_VERSION,
    ELF64_EHDR,
    ELF64_REL,
    ELF64_RELA,
    ELF64_SHDR,
    ELF64_SYM,
    ELFCLASS32,
    ELFCLASS64,
    ELFCLASSNONE,
    ELFDATA2MSB,
    ELFDATANONE,
    ELFMAG0,
    ELFMAG1,
    ELFMAG2,
    ELFMAG3,
    EM_PPC,
    ET_CORE,
    ET_DYN,
    ET_EXEC,
    ET_LOOS,
    ET_NONE,
    ET_REL,
    EV_CURRENT,
    EV_NONE,
    SHF_ALLOC,
    SHF_COMPRESSED,
    SHF_EXECINSTR,
    SHF_INFO_LINK,
    SHF_WRITE,
    SHN_LORESERVE,
    SHN_UNDEF,
    SHT_DYNAMIC,
    SHT_DYNSYM,
    SHT_GNU_HASH,
    SHT_HASH,
    SHT_INIT_ARRAY,
    SHT_LOOS,
    SHT_NOBITS,
    SHT_NOTE,
    SHT_NULL,
    SHT_PROGBITS,
    SHT_REL,
    SHT_RELA,
    SHT_SHLIB,
    SHT_STRTAB,
    SHT_SYMTAB,
    SHT_SYMTAB_SHNDX,
    ElfSection,
    build_elf,
    offsetof,
    sizeof,
)

SYM_SIZE, REL_SIZE, RELA_SIZE = sizeof(ELF64_SYM), sizeof(ELF64_REL), sizeof(ELF64_RELA)

# Every word size and byte order, as (is_64, big_endian)
VARIANTS = [(True, False), (True, True), (False, False), (False, True)]


def names(result: list[Section] | None) -> list[str]:
    assert result is not None
    return [section.name for section in result]


def rodata(**kwargs: int) -> ElfSection:
    return ElfSection(".rodata", b"hello\0", flags=SHF_ALLOC, **kwargs)


# The helpers below read and patch 64-bit little-endian files by field name
def _field(fields: list[tuple[str, str]], name: str) -> tuple[str, int]:
    return "<" + dict(fields)[name], offsetof(fields, name)


def read_ehdr(data: bytes, name: str) -> int:
    fmt, offset = _field(ELF64_EHDR, name)
    return struct.unpack_from(fmt, data, offset)[0]


def patch_ehdr(data: bytes, name: str, value: int) -> bytes:
    fmt, offset = _field(ELF64_EHDR, name)
    patched = bytearray(data)
    struct.pack_into(fmt, patched, offset, value)
    return bytes(patched)


def _shdr_field(data: bytes, index: int, name: str) -> tuple[str, int]:
    fmt, offset = _field(ELF64_SHDR, name)
    table = read_ehdr(data, "e_shoff") + index * sizeof(ELF64_SHDR)
    return fmt, table + offset


def read_shdr(data: bytes, index: int, name: str) -> int:
    fmt, offset = _shdr_field(data, index, name)
    return struct.unpack_from(fmt, data, offset)[0]


def patch_shdr(data: bytes, index: int, name: str, value: int) -> bytes:
    fmt, offset = _shdr_field(data, index, name)
    patched = bytearray(data)
    struct.pack_into(fmt, patched, offset, value)
    return bytes(patched)


class TestDataSections:
    @pytest.mark.parametrize(("is_64", "big_endian"), VARIANTS)
    def test_reads_every_variant(self, is_64: bool, big_endian: bool) -> None:
        data = build_elf(
            [
                ElfSection(".rodata", b"hello\0", flags=SHF_ALLOC),
                ElfSection(".data", b"\0world\0", flags=SHF_ALLOC | SHF_WRITE),
            ],
            is_64=is_64,
            big_endian=big_endian,
        )
        assert data_sections(data) == [
            Section(".rodata", data.index(b"hello"), 6),
            Section(".data", data.index(b"\0world"), 7),
        ]

    @pytest.mark.parametrize(("is_64", "big_endian"), VARIANTS)
    def test_extended_numbering(self, is_64: bool, big_endian: bool) -> None:
        # The section count and string table index live in section 0 instead
        data = build_elf([rodata()], is_64=is_64, big_endian=big_endian)
        extended = build_elf(
            [rodata()], is_64=is_64, big_endian=big_endian, extended=True
        )
        assert data_sections(extended) == data_sections(data)
        assert names(data_sections(extended)) == [".rodata"]

    def test_code_is_scanned(self) -> None:
        # GNU -d scans every loaded section, code included
        text = ElfSection(".text", b"\x1f\x20\x03\xd5", flags=SHF_ALLOC | SHF_EXECINSTR)
        assert names(data_sections(build_elf([text]))) == [".text"]

    def test_keeps_section_header_order(self) -> None:
        data = build_elf(
            [
                ElfSection(".data", b"d", flags=SHF_ALLOC | SHF_WRITE),
                ElfSection(".rodata", b"r", flags=SHF_ALLOC),
            ]
        )
        assert names(data_sections(data)) == [".data", ".rodata"]

    # (section, scanned)
    @pytest.mark.parametrize(
        ("section", "scanned"),
        [
            # Not loaded: BFD wants SHF_ALLOC, whatever the name
            (ElfSection(".comment", b"GCC: 1"), False),
            (ElfSection(".debug_str", b"data"), False),
            (ElfSection(".comment", b"GCC: 1", flags=SHF_ALLOC), True),
            (ElfSection(".debug_str", b"data", flags=SHF_ALLOC), True),
            # Loaded, but with no file contents, or empty
            (ElfSection(".bss", type=SHT_NOBITS, flags=SHF_ALLOC, size=64), False),
            (ElfSection(".rodata", flags=SHF_ALLOC), False),
            # BFD keys contents on the type alone, so offset 0 is scanned
            (ElfSection(".rodata", b"data", flags=SHF_ALLOC, offset=0), True),
            # Every loaded type BFD makes a section of
            (
                ElfSection(
                    ".dynsym", bytes(SYM_SIZE), SHT_DYNSYM, SHF_ALLOC, entsize=SYM_SIZE
                ),
                True,
            ),
            (ElfSection(".dynstr", b"data", SHT_STRTAB, SHF_ALLOC), True),
            (ElfSection(".dynamic", b"data", SHT_DYNAMIC, SHF_ALLOC), True),
            (ElfSection(".hash", b"data", SHT_HASH, SHF_ALLOC), True),
            (ElfSection(".gnu.hash", b"data", SHT_GNU_HASH, SHF_ALLOC), True),
            (ElfSection(".note.ABI-tag", b"data", SHT_NOTE, SHF_ALLOC), True),
            (ElfSection(".init_array", b"data", SHT_INIT_ARRAY, SHF_ALLOC), True),
            (ElfSection(".llvm_addrsig", b"data", SHT_LOOS + 1, SHF_ALLOC), True),
            # Headers BFD never makes a section from
            (ElfSection(".rodata", b"data", SHT_NULL, SHF_ALLOC), False),
            (ElfSection(".rodata", b"data", SHT_SHLIB, SHF_ALLOC), False),
            (ElfSection(".symtab_shndx", b"data", SHT_SYMTAB_SHNDX, SHF_ALLOC), False),
        ],
    )
    def test_which_sections_are_scanned(
        self, section: ElfSection, scanned: bool
    ) -> None:
        data = build_elf([section, ElfSection(".data", b"marker", flags=SHF_ALLOC)])
        expected = [".data"]
        if scanned:
            expected.insert(0, section.name)
        assert names(data_sections(data)) == expected

    def test_the_null_section_is_never_scanned(self) -> None:
        data = build_elf([rodata()])
        loaded = patch_shdr(data, 0, "sh_flags", SHF_ALLOC)
        loaded = patch_shdr(loaded, 0, "sh_offset", data.index(b"hello"))
        loaded = patch_shdr(loaded, 0, "sh_size", 6)
        assert names(data_sections(loaded)) == [".rodata"]

    def test_section_names_may_be_empty(self) -> None:
        assert names(data_sections(build_elf([rodata(name_offset=0)]))) == [""]

    def test_accepts_memoryview(self) -> None:
        data = build_elf([rodata()])
        with memoryview(data) as view:
            assert data_sections(view) == data_sections(data)


def _symtab(**kwargs: int) -> ElfSection:
    # Links to the .strtab placed right after it, at index 2
    return ElfSection(
        ".symtab", bytes(SYM_SIZE), SHT_SYMTAB, link=2, entsize=SYM_SIZE, **kwargs
    )


def _strtab(**kwargs: int) -> ElfSection:
    return ElfSection(".strtab", b"\0main\0", SHT_STRTAB, **kwargs)


class TestTables:
    """BFD's symbol, string and relocation tables, when they are loaded."""

    @pytest.mark.parametrize(
        ("e_type", "scanned"), [(ET_DYN, True), (ET_EXEC, False), (ET_REL, False)]
    )
    def test_symtab_is_a_section_only_in_a_shared_object(
        self, e_type: int, scanned: bool
    ) -> None:
        data = build_elf([_symtab(flags=SHF_ALLOC), _strtab()], e_type=e_type)
        assert names(data_sections(data)) == ([".symtab"] if scanned else [])

    def test_only_the_first_symtab_counts(self) -> None:
        data = build_elf(
            [_symtab(flags=SHF_ALLOC), _strtab(), _symtab(flags=SHF_ALLOC)],
            e_type=ET_DYN,
        )
        assert names(data_sections(data)) == [".symtab"]

    def test_the_symtab_strtab_is_not_a_section(self) -> None:
        data = build_elf([_symtab(), _strtab(flags=SHF_ALLOC)], e_type=ET_DYN)
        assert data_sections(data) == []

    def test_another_strtab_is_a_section(self) -> None:
        dynstr = ElfSection(".dynstr", b"\0libc\0", SHT_STRTAB, SHF_ALLOC)
        data = build_elf([_symtab(), _strtab(), dynstr], e_type=ET_DYN)
        assert names(data_sections(data)) == [".dynstr"]

    def test_the_name_table_is_not_a_section(self) -> None:
        data = build_elf([rodata()])
        shstrndx = read_ehdr(data, "e_shstrndx")
        assert names(
            data_sections(patch_shdr(data, shstrndx, "sh_flags", SHF_ALLOC))
        ) == [".rodata"]

    @staticmethod
    def _rela(**kwargs: int) -> ElfSection:
        # Applies to .text at index 3, with the symbols of .symtab at index 1
        fields = {
            "type": SHT_RELA,
            "link": 1,
            "info": 3,
            "flags": SHF_ALLOC | SHF_INFO_LINK,
            "entsize": RELA_SIZE,
        }
        return ElfSection(".rela.text", bytes(RELA_SIZE), **{**fields, **kwargs})

    def _reloc_scanned(self, rela: ElfSection, e_type: int = ET_REL) -> bool:
        text = ElfSection(".text", b"code", flags=SHF_ALLOC | SHF_EXECINSTR)
        data = build_elf([_symtab(), _strtab(), text, rela], e_type=e_type)
        return rela.name in names(data_sections(data))

    def test_relocations_folded_into_their_section(self) -> None:
        # BFD treats them as the target's relocations, not as a section
        assert not self._reloc_scanned(self._rela())
        assert not self._reloc_scanned(self._rela(type=SHT_REL, entsize=REL_SIZE))

    @pytest.mark.parametrize("e_type", [ET_EXEC, ET_DYN])
    def test_loaded_relocations_in_a_linked_file(self, e_type: int) -> None:
        assert self._reloc_scanned(self._rela(), e_type)

    @pytest.mark.parametrize(
        "fields",
        [
            {"link": 0},  # no symbol table
            {"link": 2},  # not the object's symbol table
            {"info": 0},  # no target
            {"info": 4},  # a target that is relocations itself
            {"flags": SHF_ALLOC | SHF_COMPRESSED},
        ],
    )
    def test_relocations_bfd_cannot_fold(self, fields: dict[str, int]) -> None:
        # BFD presents these as a plain section instead
        assert self._reloc_scanned(self._rela(**fields))

    def test_relocations_without_any_symbol_table(self) -> None:
        # sh_link 0 matches "no symbol table" too, but BFD checks for
        # SHN_UNDEF first and presents the section as it is
        text = ElfSection(".text", b"code", flags=SHF_ALLOC | SHF_EXECINSTR)
        rela = self._rela(link=SHN_UNDEF, info=1)
        assert names(data_sections(build_elf([text, rela]))) == [".text", rela.name]


def test_hand_assembled_big_endian_32_bit_object() -> None:
    # Byte by byte from the offsets of Elf32_Ehdr and Elf32_Shdr in elf.h,
    # sharing nothing with build_elf or the parser: a PowerPC ET_REL with
    # .rodata at index 1 and .shstrtab at index 2
    data = bytearray(204)
    put = struct.pack_into
    # Elf32_Ehdr at 0 (52 bytes): e_ident[16], then e_type, e_machine (Half),
    # e_version, e_entry, e_phoff, e_shoff, e_flags (4 bytes each), then six
    # Halfs from e_ehsize at 40
    data[0:7] = bytes(
        [ELFMAG0, ELFMAG1, ELFMAG2, ELFMAG3, ELFCLASS32, ELFDATA2MSB, EV_CURRENT]
    )
    put(">H", data, 16, ET_REL)  # e_type
    put(">H", data, 18, EM_PPC)  # e_machine
    put(">I", data, 20, EV_CURRENT)  # e_version
    put(">I", data, 32, 84)  # e_shoff: after the contents, 4-aligned
    put(">H", data, 40, 52)  # e_ehsize
    put(">H", data, 46, 40)  # e_shentsize: sizeof(Elf32_Shdr), ten Words
    put(">H", data, 48, 3)  # e_shnum
    put(">H", data, 50, 2)  # e_shstrndx
    data[52:62] = b"hello ppc\0"
    data[62:81] = b"\0.rodata\0.shstrtab\0"
    # Elf32_Shdr: sh_name at 0, sh_type 4, sh_flags 8, sh_addr 12, sh_offset 16,
    # sh_size 20 (Words, Addrs and Offs are all 4 bytes)
    for index, (name, sh_type, flags, offset, size) in enumerate(
        [(1, SHT_PROGBITS, SHF_ALLOC, 52, 10), (9, SHT_STRTAB, 0, 62, 19)], start=1
    ):
        header = 84 + index * 40
        put(">I", data, header, name)
        put(">I", data, header + 4, sh_type)
        put(">I", data, header + 8, flags)
        put(">I", data, header + 16, offset)
        put(">I", data, header + 20, size)
    assert data_sections(bytes(data)) == [Section(".rodata", 52, 10)]


class TestNotElf:
    @pytest.mark.parametrize(
        "data",
        [
            b"",
            b"\x7fEL",
            b"\x7fELF\x02\x01\x01",
            b"hello world, this is not a binary",
            b"\xcf\xfa\xed\xfe" + bytes(60),
            b"!<arch>\n" + bytes(60),
        ],
    )
    def test_is_none(self, data: bytes) -> None:
        assert data_sections(data) is None

    @pytest.mark.parametrize(
        ("offset", "value"),
        [
            (EI_CLASS, ELFCLASSNONE),
            (EI_CLASS, ELFCLASS64 + 1),
            (EI_DATA, ELFDATANONE),
            (EI_DATA, ELFDATA2MSB + 1),
            (EI_VERSION, EV_NONE),
        ],
    )
    def test_bad_identification_is_none(self, offset: int, value: int) -> None:
        data = bytearray(build_elf([rodata()]))
        data[offset] = value
        assert data_sections(bytes(data)) is None

    def test_core_file_is_none(self) -> None:
        # BFD opens a core file as a core dump, not an object
        assert data_sections(build_elf([rodata()], e_type=ET_CORE)) is None

    @pytest.mark.parametrize("e_type", [ET_NONE, ET_REL, ET_EXEC, ET_DYN, ET_LOOS])
    def test_other_types_are_objects(self, e_type: int) -> None:
        assert names(data_sections(build_elf([rodata()], e_type=e_type))) == [".rodata"]


class TestNoSections:
    """Valid ELF that BFD builds no sections for, so GNU scans it whole."""

    def test_no_section_header_table(self) -> None:
        # As left by sstrip, or a hand-built file: BFD does not make sections
        # from the program headers
        data = build_elf([rodata()])
        stripped = data[: read_ehdr(data, "e_shoff")]
        stripped = patch_ehdr(stripped, "e_shoff", 0)
        stripped = patch_ehdr(stripped, "e_shnum", 0)
        assert data_sections(patch_ehdr(stripped, "e_shstrndx", SHN_UNDEF)) == []

    @pytest.mark.parametrize("shstrndx", [SHN_UNDEF, 1, 3, SHN_LORESERVE - 1])
    def test_unusable_name_table_index(self, shstrndx: int) -> None:
        # 0 is SHN_UNDEF, 1 is .rodata, not a string table, and 3 is past the
        # end. BFD resets a bad index to SHN_UNDEF, then makes no sections.
        data = build_elf([rodata()])
        assert data_sections(patch_ehdr(data, "e_shstrndx", shstrndx)) == []

    def test_section_0_is_never_the_name_table(self) -> None:
        # Even typed and placed as a string table: e_shstrndx 0 is SHN_UNDEF
        data = build_elf([rodata()])
        shstrndx = read_ehdr(data, "e_shstrndx")
        null = patch_shdr(data, 0, "sh_type", SHT_STRTAB)
        for name in ("sh_offset", "sh_size"):
            null = patch_shdr(null, 0, name, read_shdr(data, shstrndx, name))
        assert data_sections(patch_ehdr(null, "e_shstrndx", SHN_UNDEF)) == []


class TestMalformed:
    @pytest.fixture
    def data(self) -> bytes:
        return build_elf(
            [
                ElfSection(".rodata", b"hello\0", flags=SHF_ALLOC),
                ElfSection(".data", b"world\0", flags=SHF_ALLOC | SHF_WRITE),
                ElfSection(".note", b"note", SHT_NOTE),
            ]
        )

    def test_the_fixture_parses(self, data: bytes) -> None:
        assert names(data_sections(data)) == [".rodata", ".data"]

    def test_every_truncation(self, data: bytes) -> None:
        # The section header table comes last, so every prefix cuts into it
        for length in range(len(data)):
            assert data_sections(data[:length]) is None, length

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("e_shentsize", sizeof(ELF64_SHDR) - 1),
            ("e_shoff", sizeof(ELF64_EHDR) - 1),  # inside the ELF header
            ("e_shoff", 2**64 - 1),  # past the end of the file
            ("e_shnum", 2**16 - 1),  # more headers than the file holds
            ("e_shoff", 0),  # sections, but no table
        ],
    )
    def test_corrupt_header(self, data: bytes, name: str, value: int) -> None:
        assert data_sections(patch_ehdr(data, name, value)) is None

    @pytest.mark.parametrize("count", [0, 2**64 - 1])
    def test_bad_extended_count(self, count: int) -> None:
        # No count at all, or a table that runs past the end of the file
        data = build_elf([rodata()], extended=True)
        assert data_sections(patch_shdr(data, 0, "sh_size", count)) is None

    def test_extended_count_past_elf_h_limit(self) -> None:
        # Extended numbering exists for SHN_LORESERVE or more sections, and BFD
        # accepts such counts: its own SHN_LORESERVE is 0xffffff00. The extra
        # headers are SHT_NULL, as zeros.
        data = build_elf([rodata()], extended=True)
        data += bytes(SHN_LORESERVE * sizeof(ELF64_SHDR))
        large = patch_shdr(data, 0, "sh_size", SHN_LORESERVE)
        assert names(data_sections(large)) == [".rodata"]

    @pytest.mark.parametrize(
        ("field", "value"),
        [("sh_size", 0x10000), ("sh_size", 2**64 - 1), ("sh_offset", 0xFFFFFFF0)],
    )
    def test_section_outside_the_file_is_skipped(
        self, data: bytes, field: int, value: int
    ) -> None:
        # GNU reports that section unreadable and scans the rest
        assert names(data_sections(patch_shdr(data, 1, field, value))) == [".data"]

    def test_section_ending_at_the_end_of_the_file(self) -> None:
        data = build_elf([rodata()]) + b"tail"
        moved = patch_shdr(data, 1, "sh_offset", len(data) - 4)
        moved = patch_shdr(moved, 1, "sh_size", 4)
        assert data_sections(moved) == [Section(".rodata", len(data) - 4, 4)]
        assert names(data_sections(patch_shdr(moved, 1, "sh_size", 5))) == []

    def test_note_outside_the_file_is_none(self, data: bytes) -> None:
        # BFD reads every note while opening the object, loaded or not, and
        # rejects the object when it cannot
        assert data_sections(patch_shdr(data, 3, "sh_size", 0x10000)) is None

    def test_empty_note_is_not_read(self, data: bytes) -> None:
        empty = patch_shdr(patch_shdr(data, 3, "sh_size", 0), 3, "sh_offset", 2**40)
        assert names(data_sections(empty)) == [".rodata", ".data"]

    def test_skipped_sections_are_not_bounds_checked(self) -> None:
        # A NOBITS section's size describes memory, not the file
        bss = ElfSection(".bss", type=SHT_NOBITS, flags=SHF_ALLOC, size=2**40)
        assert data_sections(build_elf([bss])) == []

    @pytest.mark.parametrize("index", [0, 1, 2])
    def test_unreadable_name_is_none(self, data: bytes, index: int) -> None:
        # BFD looks up every name but section 0's, scanned or not, and rejects
        # the object when one lies outside the name table
        patched = patch_shdr(data, index, "sh_name", 0x10000)
        if index == 0:
            assert names(data_sections(patched)) == [".rodata", ".data"]
        else:
            assert data_sections(patched) is None

    def test_name_at_the_table_terminator(self, data: bytes) -> None:
        # The table's last byte is a valid, empty name; one past it is not
        size = read_shdr(data, read_ehdr(data, "e_shstrndx"), "sh_size")
        assert names(data_sections(patch_shdr(data, 1, "sh_name", size - 1))) == [
            "",
            ".data",
        ]
        assert data_sections(patch_shdr(data, 1, "sh_name", size)) is None

    def test_name_table_outside_the_file_is_none(self, data: bytes) -> None:
        shstrndx = read_ehdr(data, "e_shstrndx")
        assert data_sections(patch_shdr(data, shstrndx, "sh_offset", 2**40)) is None

    def test_empty_name_table(self, data: bytes) -> None:
        shstrndx = read_ehdr(data, "e_shstrndx")
        empty = patch_shdr(data, shstrndx, "sh_size", 0)
        assert data_sections(empty) is None
        # At offset 0 too, where the file's own bytes must not stand in for it
        assert data_sections(patch_shdr(empty, shstrndx, "sh_offset", 0)) is None
        # ...unless every section has the empty name, which needs no table
        for index in range(1, shstrndx + 1):
            empty = patch_shdr(empty, index, "sh_name", 0)
        assert names(data_sections(empty)) == ["", ""]

    def test_unterminated_name_table(self, data: bytes) -> None:
        # BFD treats the table's last byte as a terminator, whatever it holds
        shstrndx = read_ehdr(data, "e_shstrndx")
        offset = read_shdr(data, shstrndx, "sh_offset")
        size = read_shdr(data, shstrndx, "sh_size")
        # Make .rodata's name the last one in the table, then drop its NUL
        last = data.rindex(b"\0", offset, offset + size - 1) + 1
        renamed = patch_shdr(data, 1, "sh_name", last - offset)
        unterminated = bytearray(renamed)
        unterminated[offset + size - 1] = ord("X")
        assert names(data_sections(bytes(unterminated)))[0] == ".shstrtab"

    def test_names_are_bounded(self) -> None:
        # A name table with no NUL for its whole length, named into at many
        # offsets, must not give each section a copy of the rest of it: names
        # are cut at NAME_LIMIT bytes, so memory stays linear in the file
        long_name = "." + "A" * (4 * NAME_LIMIT)
        sections = [
            ElfSection(long_name, b"x", flags=SHF_ALLOC),
            *[
                ElfSection(".x", b"x", flags=SHF_ALLOC, name_offset=offset)
                for offset in range(2, 3 * NAME_LIMIT, 7)
            ],
        ]
        result = data_sections(build_elf(sections))
        assert result is not None
        assert len(result) == len(sections)
        assert result[0].name == long_name[:NAME_LIMIT]
        assert all(len(section.name) <= NAME_LIMIT for section in result)
