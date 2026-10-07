import struct

import pytest

from sillystrings.formats.common import Section
from sillystrings.formats.elf import data_sections

from .conftest import ElfSection, build_elf

# elf.h: ET_REL 1, ET_EXEC 2, ET_DYN 3, ET_CORE 4
ET_REL, ET_EXEC, ET_DYN, ET_CORE = 1, 2, 3, 4
# elf.h: SHT_* section types
SHT_NULL = 0
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_RELA = 4
SHT_HASH = 5
SHT_DYNAMIC = 6
SHT_NOTE = 7
SHT_NOBITS = 8
SHT_REL = 9
SHT_SHLIB = 10
SHT_DYNSYM = 11
SHT_INIT_ARRAY = 14
SHT_SYMTAB_SHNDX = 18
SHT_GNU_HASH = 0x6FFFFFF6
SHT_LOOS = 0x60000000
# elf.h: SHF_WRITE (1 << 0), SHF_ALLOC (1 << 1), SHF_EXECINSTR (1 << 2),
# SHF_INFO_LINK (1 << 6), SHF_COMPRESSED (1 << 11)
SHF_WRITE = 1 << 0
SHF_ALLOC = 1 << 1
SHF_EXECINSTR = 1 << 2
SHF_INFO_LINK = 1 << 6
SHF_COMPRESSED = 1 << 11
# elf.h: Elf64_Sym and Elf64_Rela are 24 bytes, Elf64_Rel 16
SYM_SIZE = RELA_SIZE = 24
REL_SIZE = 16

# Every word size and byte order, as (is_64, big_endian)
VARIANTS = [(True, False), (True, True), (False, False), (False, True)]

# Byte offsets in a 64-bit file, from the field order of Elf64_Ehdr and
# Elf64_Shdr in elf.h
EI_CLASS, EI_DATA, EI_VERSION = 4, 5, 6
E_TYPE = 16
E_SHOFF = 40
E_SHENTSIZE, E_SHNUM, E_SHSTRNDX = 58, 60, 62
SH_NAME, SH_TYPE, SH_FLAGS, SH_OFFSET, SH_SIZE = 0, 4, 8, 24, 32
SHDR_SIZE = 64


def names(result: list[Section] | None) -> list[str]:
    assert result is not None
    return [section.name for section in result]


def rodata(**kwargs: int) -> ElfSection:
    return ElfSection(".rodata", b"hello\0", flags=SHF_ALLOC, **kwargs)


def patch(data: bytes, fmt: str, offset: int, value: int) -> bytes:
    patched = bytearray(data)
    struct.pack_into("<" + fmt, patched, offset, value)
    return bytes(patched)


def patch_shdr(data: bytes, index: int, field: int, value: int) -> bytes:
    """Overwrite one field of a 64-bit little-endian section header."""
    (shoff,) = struct.unpack_from("<Q", data, E_SHOFF)
    fmt = "I" if field in {SH_NAME, SH_TYPE} else "Q"
    return patch(data, fmt, shoff + index * SHDR_SIZE + field, value)


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
        loaded = patch_shdr(data, 0, SH_FLAGS, SHF_ALLOC)
        loaded = patch_shdr(loaded, 0, SH_OFFSET, data.index(b"hello"))
        loaded = patch_shdr(loaded, 0, SH_SIZE, 6)
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
        shstrndx = struct.unpack_from("<H", data, E_SHSTRNDX)[0]
        assert names(data_sections(patch_shdr(data, shstrndx, SH_FLAGS, 2))) == [
            ".rodata"
        ]

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


def test_hand_assembled_big_endian_32_bit_object() -> None:
    # Byte by byte from the offsets of Elf32_Ehdr and Elf32_Shdr in elf.h,
    # sharing nothing with build_elf or the parser: a PowerPC ET_REL with
    # .rodata at index 1 and .shstrtab at index 2
    data = bytearray(204)
    put = struct.pack_into
    # e_ident: magic, ELFCLASS32, ELFDATA2MSB, EV_CURRENT
    data[0:7] = b"\x7fELF\x01\x02\x01"
    put(">H", data, 16, ET_REL)  # e_type
    put(">H", data, 18, 20)  # e_machine: EM_PPC
    put(">I", data, 20, 1)  # e_version
    put(">I", data, 32, 84)  # e_shoff
    put(">H", data, 40, 52)  # e_ehsize
    put(">H", data, 46, 40)  # e_shentsize
    put(">H", data, 48, 3)  # e_shnum
    put(">H", data, 50, 2)  # e_shstrndx
    data[52:62] = b"hello ppc\0"
    data[62:81] = b"\0.rodata\0.shstrtab\0"
    # Elf32_Shdr: sh_name at 0, sh_type 4, sh_flags 8, sh_offset 16, sh_size 20
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
            (EI_CLASS, 0),  # ELFCLASSNONE
            (EI_CLASS, 3),
            (EI_DATA, 0),  # ELFDATANONE
            (EI_DATA, 3),
            (EI_VERSION, 0),  # EV_NONE
        ],
    )
    def test_bad_identification_is_none(self, offset: int, value: int) -> None:
        data = bytearray(build_elf([rodata()]))
        data[offset] = value
        assert data_sections(bytes(data)) is None

    def test_core_file_is_none(self) -> None:
        # BFD opens a core file as a core dump, not an object
        assert data_sections(build_elf([rodata()], e_type=ET_CORE)) is None

    @pytest.mark.parametrize("e_type", [0, ET_REL, ET_EXEC, ET_DYN, 0xFE00])
    def test_other_types_are_objects(self, e_type: int) -> None:
        assert names(data_sections(build_elf([rodata()], e_type=e_type))) == [".rodata"]


class TestNoSections:
    """Valid ELF that BFD builds no sections for, so GNU scans it whole."""

    def test_no_section_header_table(self) -> None:
        # As left by sstrip, or a hand-built file: BFD does not make sections
        # from the program headers
        data = build_elf([rodata()])
        (shoff,) = struct.unpack_from("<Q", data, E_SHOFF)
        stripped = patch(patch(data[:shoff], "Q", E_SHOFF, 0), "H", E_SHNUM, 0)
        assert data_sections(patch(stripped, "H", E_SHSTRNDX, 0)) == []

    @pytest.mark.parametrize("shstrndx", [0, 1, 3, 0xFEFF])
    def test_unusable_name_table_index(self, shstrndx: int) -> None:
        # 0 is SHN_UNDEF, 1 is .rodata, not a string table, and 3 is past the
        # end. BFD resets a bad index to SHN_UNDEF, then makes no sections.
        data = build_elf([rodata()])
        assert data_sections(patch(data, "H", E_SHSTRNDX, shstrndx)) == []


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
        ("fmt", "offset", "value"),
        [
            ("H", E_SHENTSIZE, 40),  # Elf32_Shdr's size in a 64-bit file
            ("Q", E_SHOFF, 63),  # inside the ELF header
            ("Q", E_SHOFF, 2**64 - 1),  # past the end of the file
            ("H", E_SHNUM, 0xFFFF),  # more headers than the file holds
            ("Q", E_SHOFF, 0),  # sections, but no table
        ],
    )
    def test_corrupt_header(
        self, data: bytes, fmt: str, offset: int, value: int
    ) -> None:
        assert data_sections(patch(data, fmt, offset, value)) is None

    @pytest.mark.parametrize("count", [0, 0xFF00, 2**64 - 1])
    def test_bad_extended_count(self, count: int) -> None:
        # Section 0 must hold a count between 1 and SHN_LORESERVE - 1
        data = build_elf([rodata()], extended=True)
        assert data_sections(patch_shdr(data, 0, SH_SIZE, count)) is None

    @pytest.mark.parametrize(
        ("field", "value"),
        [(SH_SIZE, 0x10000), (SH_SIZE, 2**64 - 1), (SH_OFFSET, 0xFFFFFFF0)],
    )
    def test_section_outside_the_file_is_skipped(
        self, data: bytes, field: int, value: int
    ) -> None:
        # GNU reports that section unreadable and scans the rest
        assert names(data_sections(patch_shdr(data, 1, field, value))) == [".data"]

    def test_section_ending_at_the_end_of_the_file(self) -> None:
        data = build_elf([rodata()]) + b"tail"
        moved = patch_shdr(data, 1, SH_OFFSET, len(data) - 4)
        moved = patch_shdr(moved, 1, SH_SIZE, 4)
        assert data_sections(moved) == [Section(".rodata", len(data) - 4, 4)]
        assert names(data_sections(patch_shdr(moved, 1, SH_SIZE, 5))) == []

    def test_note_outside_the_file_is_none(self, data: bytes) -> None:
        # BFD reads every note while opening the object, loaded or not, and
        # rejects the object when it cannot
        assert data_sections(patch_shdr(data, 3, SH_SIZE, 0x10000)) is None

    def test_empty_note_is_not_read(self, data: bytes) -> None:
        empty = patch_shdr(patch_shdr(data, 3, SH_SIZE, 0), 3, SH_OFFSET, 2**40)
        assert names(data_sections(empty)) == [".rodata", ".data"]

    def test_skipped_sections_are_not_bounds_checked(self) -> None:
        # A NOBITS section's size describes memory, not the file
        bss = ElfSection(".bss", type=SHT_NOBITS, flags=SHF_ALLOC, size=2**40)
        assert data_sections(build_elf([bss])) == []

    @pytest.mark.parametrize("index", [0, 1, 2])
    def test_unreadable_name_is_none(self, data: bytes, index: int) -> None:
        # BFD looks up every name but section 0's, scanned or not, and rejects
        # the object when one lies outside the name table
        patched = patch_shdr(data, index, SH_NAME, 0x10000)
        if index == 0:
            assert names(data_sections(patched)) == [".rodata", ".data"]
        else:
            assert data_sections(patched) is None

    def test_name_table_outside_the_file_is_none(self, data: bytes) -> None:
        shstrndx = struct.unpack_from("<H", data, E_SHSTRNDX)[0]
        assert data_sections(patch_shdr(data, shstrndx, SH_OFFSET, 2**40)) is None

    def test_empty_name_table(self, data: bytes) -> None:
        shstrndx = struct.unpack_from("<H", data, E_SHSTRNDX)[0]
        empty = patch_shdr(data, shstrndx, SH_SIZE, 0)
        assert data_sections(empty) is None
        # ...unless every section has the empty name, which needs no table
        for index in range(1, shstrndx + 1):
            empty = patch_shdr(empty, index, SH_NAME, 0)
        assert names(data_sections(empty)) == ["", ""]

    def test_unterminated_name_table(self, data: bytes) -> None:
        # BFD treats the table's last byte as a terminator, whatever it holds
        shstrndx = struct.unpack_from("<H", data, E_SHSTRNDX)[0]
        (shoff,) = struct.unpack_from("<Q", data, E_SHOFF)
        header = shoff + shstrndx * SHDR_SIZE
        (offset,) = struct.unpack_from("<Q", data, header + SH_OFFSET)
        (size,) = struct.unpack_from("<Q", data, header + SH_SIZE)
        # Make .rodata's name the last one in the table, then drop its NUL
        last = data.rindex(b"\0", offset, offset + size - 1) + 1
        renamed = patch_shdr(data, 1, SH_NAME, last - offset)
        unterminated = bytearray(renamed)
        unterminated[offset + size - 1] = ord("X")
        assert names(data_sections(bytes(unterminated)))[0] == ".shstrtab"
