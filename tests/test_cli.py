# tests/test_cli.py
import argparse
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from sillystrings.cli import (
    build_parser,
    format_offset,
    main,
    open_source,
    positive_int,
)

from .conftest import S_ZEROFILL, MachOSection, build_macho


def run(*args: str, data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    cmd = ["uv", "run", "sillystrings", *args]
    return subprocess.run(cmd, input=data, capture_output=True, check=False)


# --- Core tests ---


def test_basic(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00hello world\x00")
    result = run(str(f))
    assert result.returncode == 0
    assert b"hello world" in result.stdout


def test_min_length(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00hello\x00")
    assert b"hello" not in run(str(f), "-n", "6").stdout
    assert b"hello" in run(str(f), "-n", "5").stdout


def test_offset_hex(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00\x00\x00hello\x00")
    result = run(str(f), "-t", "x")
    assert result.returncode == 0
    assert b"3 hello" in result.stdout


def test_offset_decimal(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00\x00\x00hello\x00")
    result = run(str(f), "-t", "d")
    assert b"3 hello" in result.stdout


def test_offset_octal(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00\x00\x00hello\x00")
    result = run(str(f), "-t", "o")
    assert b"3 hello" in result.stdout


def test_octal_shorthand_matches_radix_octal(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00" * 8 + b"hello\x00")
    result = run(str(f), "-o")
    assert result.returncode == 0
    assert b"10 hello" in result.stdout
    assert result.stdout == run(str(f), "-t", "o").stdout


def test_stdin() -> None:
    result = run("-", data=b"\x00hello world\x00")
    assert result.returncode == 0
    assert b"hello world" in result.stdout


def test_stdin_no_args() -> None:
    result = run(data=b"\x00hello world\x00")
    assert result.returncode == 0
    assert b"hello world" in result.stdout


def test_missing_file() -> None:
    result = run("nonexistent.bin")
    assert result.returncode != 0
    assert b"No such file" in result.stderr


def test_multiple_files(tmp_path: Path) -> None:
    f1 = tmp_path / "a.bin"
    f2 = tmp_path / "b.bin"
    f1.write_bytes(b"\x00hello\x00")
    f2.write_bytes(b"\x00world\x00")
    result = run(str(f1), str(f2))
    assert result.returncode == 0
    assert b"a.bin" in result.stdout
    assert b"b.bin" in result.stdout


def test_print_file_name(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00hello\x00")
    result = run("-f", str(f))
    assert b"t.bin: hello" in result.stdout


def test_print_file_name_not_shown(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00hello\x00")
    result = run(str(f))
    assert result.stdout.strip() == b"hello"


def test_encoding_flag(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    # 0x80-0xFF are printable in S mode but not in s mode
    f.write_bytes(b"\x00" + bytes(range(0x80, 0x85)) + b"\x00")
    assert run(str(f), "-e", "S", "-n", "4").stdout.strip() != b""
    assert run(str(f), "-e", "s", "-n", "4").stdout.strip() == b""


def test_utf32_encoding_flag(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00" * 4 + "hello".encode("utf-32-be"))
    result = run("-e", "B", "-t", "d", str(f))
    assert result.returncode == 0
    assert result.stdout == b"      4 hello\n"


def test_whitespace_flag(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    # Without -w, \n breaks the string into two; with -w, it's one string
    # Use -t d to distinguish: two offsets without -w, one offset with -w
    f.write_bytes(b"\x00hello\nworld\x00")
    without_w = run("-t", "d", str(f))
    with_w = run("-w", "-t", "d", str(f))
    # Without -w: two strings at offsets 1 and 7
    assert b"1 hello" in without_w.stdout
    assert b"7 world" in without_w.stdout
    # With -w: one string starting at offset 1
    assert b"1 hello" in with_w.stdout
    assert b"7 world" not in with_w.stdout


def test_tab_does_not_split_string() -> None:
    # GNU strings treats tab as printable even without -w (#55)
    result = run(data=b"abcd\tefgh\x00")
    assert result.returncode == 0
    assert result.stdout == b"abcd\tefgh\n"


def test_version() -> None:
    result = run("-v")
    assert result.returncode == 0
    assert b"sillystrings" in result.stdout


def test_data_flag(tmp_path: Path) -> None:
    f = tmp_path / "t.o"
    f.write_bytes(
        build_macho([("", [MachOSection("__TEXT", "__cstring", b"hello world")])])
    )
    data_only = run("-d", str(f))
    assert data_only.returncode == 0
    assert data_only.stdout == b"hello world\n"
    # The whole file also holds the section names from the load commands
    assert b"__cstring" in run(str(f)).stdout


# --- Edge case tests ---


def test_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty.bin"
    f.write_bytes(b"")
    result = run(str(f))
    assert result.returncode == 0
    assert result.stdout == b""


def test_all_non_printable(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00\x01\x02\x03\x04\x05")
    result = run(str(f))
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""


def test_very_large_min_length(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00hello\x00")
    result = run("-n", "9999", str(f))
    assert result.returncode == 0
    assert result.stdout == b""


def test_single_printable_byte(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"A")
    assert b"A" in run("-n", "1", str(f)).stdout
    assert run(str(f)).stdout == b""


def test_single_non_printable_byte(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00")
    result = run(str(f))
    assert result.returncode == 0
    assert result.stdout == b""


def test_utf16_single_byte(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x41")
    result = run("-e", "l", str(f))
    assert result.returncode == 0
    assert result.stdout == b""


@pytest.mark.parametrize("value", ["0", "-1", "-5"])
def test_invalid_min_length(value: str, tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00hello\x00")
    result = run("-n", value, str(f))
    assert result.returncode != 0


def test_prefix_with_offset(tmp_path: Path) -> None:
    f = tmp_path / "t.bin"
    f.write_bytes(b"\x00hello\x00")
    result = run("-f", "-t", "d", str(f))
    assert b"t.bin:" in result.stdout
    assert b"1 hello" in result.stdout


# --- Unit tests (for coverage) ---


class TestFormatOffset:
    def test_decimal(self) -> None:
        assert format_offset(42, "d") == "     42 "

    def test_octal(self) -> None:
        assert format_offset(42, "o") == "     52 "

    def test_hex(self) -> None:
        assert format_offset(42, "x") == "     2a "

    def test_none(self) -> None:
        assert format_offset(0, None) == ""


class TestBuildParser:
    def test_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.min_length == 4
        assert args.encoding == "s"
        assert args.radix is None
        assert args.include_all_whitespace is False
        assert args.print_file_name is False

    def test_all_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["-n", "8", "-t", "x", "-e", "S", "-w", "-f"])
        assert args.min_length == 8
        assert args.radix == "x"
        assert args.encoding == "S"
        assert args.include_all_whitespace is True
        assert args.print_file_name is True

    def test_data_only_defaults_off(self) -> None:
        assert build_parser().parse_args([]).data_only is False

    # -a and -d share a destination, so the last one given wins, as in GNU strings
    @pytest.mark.parametrize(
        ("argv", "data_only"),
        [
            (["-d"], True),
            (["--data"], True),
            (["-a"], False),
            (["--all"], False),
            (["-a", "-d"], True),
            (["-d", "-a"], False),
        ],
    )
    def test_all_and_data_last_wins(self, argv: list[str], data_only: bool) -> None:
        assert build_parser().parse_args(argv).data_only is data_only

    def test_octal_shorthand(self) -> None:
        assert build_parser().parse_args(["-o"]).radix == "o"

    # -o and -t share a destination, so the last one given wins, as in GNU strings
    @pytest.mark.parametrize(
        ("argv", "radix"),
        [
            (["-o", "-t", "x"], "x"),
            (["-t", "x", "-o"], "o"),
        ],
    )
    def test_octal_shorthand_last_wins(self, argv: list[str], radix: str) -> None:
        assert build_parser().parse_args(argv).radix == radix


Capture = pytest.CaptureFixture[str]


class TestMain:
    def test_file_input(
        self, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        f = tmp_path / "t.bin"
        f.write_bytes(b"\x00hello\x00")
        mocker.patch("sys.argv", ["sillystrings", str(f)])
        main()
        assert "hello" in capsys.readouterr().out

    def test_stdin_input(self, mocker: MockerFixture, capsys: Capture) -> None:
        fake_stdin = mocker.Mock()
        fake_stdin.buffer = BytesIO(b"\x00hello\x00")
        mocker.patch("sys.argv", ["sillystrings"])
        mocker.patch("sys.stdin", fake_stdin)
        main()
        assert "hello" in capsys.readouterr().out

    def test_stdin_dash(self, mocker: MockerFixture, capsys: Capture) -> None:
        fake_stdin = mocker.Mock()
        fake_stdin.buffer = BytesIO(b"\x00hello\x00")
        mocker.patch("sys.argv", ["sillystrings", "-"])
        mocker.patch("sys.stdin", fake_stdin)
        main()
        assert "hello" in capsys.readouterr().out

    def test_missing_file_exits(self, mocker: MockerFixture, capsys: Capture) -> None:
        mocker.patch("sys.argv", ["sillystrings", "nonexistent.bin"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        assert "No such file" in capsys.readouterr().err

    def test_multiple_files_prefix(
        self, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"\x00hello\x00")
        f2.write_bytes(b"\x00world\x00")
        mocker.patch("sys.argv", ["sillystrings", str(f1), str(f2)])
        main()
        out = capsys.readouterr().out
        assert "a.bin:" in out
        assert "b.bin:" in out

    def test_print_file_name_flag(
        self, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        f = tmp_path / "t.bin"
        f.write_bytes(b"\x00hello\x00")
        mocker.patch("sys.argv", ["sillystrings", "-f", str(f)])
        main()
        assert "t.bin:" in capsys.readouterr().out

    def test_no_prefix_single_file(
        self, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        f = tmp_path / "t.bin"
        f.write_bytes(b"\x00hello\x00")
        mocker.patch("sys.argv", ["sillystrings", str(f)])
        main()
        assert capsys.readouterr().out.strip() == "hello"

    def test_offset_formatting(
        self, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        f = tmp_path / "t.bin"
        f.write_bytes(b"\x00\x00\x00hello\x00")
        mocker.patch("sys.argv", ["sillystrings", "-t", "d", str(f)])
        main()
        assert "3 hello" in capsys.readouterr().out

    def test_encoding_passthrough(
        self, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        f = tmp_path / "t.bin"
        f.write_bytes(b"\x00" + bytes(range(0x80, 0x85)) + b"\x00")
        mocker.patch("sys.argv", ["sillystrings", "-e", "S", "-n", "4", str(f)])
        main()
        assert capsys.readouterr().out.strip() != ""

    def test_empty_file(
        self, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        mocker.patch("sys.argv", ["sillystrings", str(f)])
        main()
        assert capsys.readouterr().out == ""

    def test_missing_later_file_prints_nothing(
        self, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        # Paths are checked before any scanning, so a bad path late in the
        # list still fails the run without partial output
        f = tmp_path / "t.bin"
        f.write_bytes(b"\x00hello\x00")
        mocker.patch("sys.argv", ["sillystrings", str(f), "nonexistent.bin"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "nonexistent.bin: No such file" in captured.err

    def test_multiple_files_in_order_with_own_offsets(
        self, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"\x00hello\x00")
        f2.write_bytes(b"\x00\x00world\x00")
        mocker.patch("sys.argv", ["sillystrings", "-t", "d", str(f1), str(f2)])
        main()
        assert capsys.readouterr().out.splitlines() == [
            f"{f1}:       1 hello",
            f"{f2}:       2 world",
        ]

    def test_whitespace_passthrough(
        self, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        f = tmp_path / "t.bin"
        f.write_bytes(b"\x00hello\nworld\x00")
        mocker.patch("sys.argv", ["sillystrings", "-w", "-t", "d", str(f)])
        main()
        out = capsys.readouterr().out
        # With -w: one string starting at offset 1 (not two separate strings)
        assert "7 world" not in out


# A Mach-O object whose two data sections sit back to back, with a code
# section and a zerofill section that -d must handle
MACHO = build_macho(
    [
        (
            "",
            [
                MachOSection("__TEXT", "__text", b"code"),
                MachOSection("__TEXT", "__cstring", b"abcd"),
                MachOSection("__DATA", "__data", b"efgh"),
                MachOSection("__DATA", "__bss", size=64, flags=S_ZEROFILL),
            ],
        )
    ]
)
CODE, CSTRING, DATA = MACHO.index(b"code"), MACHO.index(b"abcd"), MACHO.index(b"efgh")


class TestDataSections:
    @pytest.fixture
    def macho(self, tmp_path: Path) -> Path:
        f = tmp_path / "t.o"
        f.write_bytes(MACHO)
        return f

    def run_main(self, mocker: MockerFixture, capsys: Capture, *argv: str) -> str:
        mocker.patch("sys.argv", ["sillystrings", *argv])
        main()
        return capsys.readouterr().out

    def test_data_scans_each_section_at_its_file_offset(
        self, macho: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        # Code is scanned too, as in GNU strings. The adjacent sections are
        # scanned separately, so their strings do not run together.
        out = self.run_main(mocker, capsys, "-d", "-t", "d", str(macho))
        assert out.splitlines() == [
            f"{CODE:7d} code",
            f"{CSTRING:7d} abcd",
            f"{DATA:7d} efgh",
        ]

    @pytest.mark.parametrize("argv", [[], ["-a"], ["-d", "-a"]])
    def test_whole_file_by_default_and_with_all(
        self, argv: list[str], macho: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        out = self.run_main(mocker, capsys, *argv, "-t", "d", str(macho))
        lines = out.splitlines()
        assert f"{CODE:7d} codeabcdefgh" in lines
        assert any(line.endswith(" __cstring") for line in lines)

    def test_data_on_an_unrecognized_file_scans_it_whole(
        self, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        f = tmp_path / "t.bin"
        f.write_bytes(b"\x00hello\x00world\x00")
        out = self.run_main(mocker, capsys, "-d", "-t", "d", str(f))
        assert out.splitlines() == ["      1 hello", "      7 world"]

    def test_data_with_no_data_sections_scans_the_whole_file(
        self, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        f = tmp_path / "t.o"
        bss = MachOSection("__DATA", "__bss", size=64, flags=S_ZEROFILL)
        f.write_bytes(build_macho([("__DATA", [bss])]))
        out = self.run_main(mocker, capsys, "-d", str(f))
        assert out.splitlines() == ["__DATA", "__bss", "__DATA"]

    def test_data_is_ignored_for_stdin(
        self, mocker: MockerFixture, capsys: Capture
    ) -> None:
        # As in GNU strings, which scans stdin whole whatever the flags
        fake_stdin = mocker.Mock()
        fake_stdin.buffer = BytesIO(MACHO)
        mocker.patch("sys.stdin", fake_stdin)
        out = self.run_main(mocker, capsys, "-d", "-t", "d")
        assert f"{CODE:7d} codeabcdefgh" in out.splitlines()

    def test_data_per_file(
        self, macho: Path, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        other = tmp_path / "t.bin"
        other.write_bytes(b"\x00hello\x00")
        out = self.run_main(mocker, capsys, "-d", str(macho), str(other))
        assert out.splitlines() == [
            f"{macho}: code",
            f"{macho}: abcd",
            f"{macho}: efgh",
            f"{other}: hello",
        ]


class TestOpenSource:
    def test_file_is_mapped(self, tmp_path: Path) -> None:
        f = tmp_path / "t.bin"
        f.write_bytes(b"\x00hello\x00")
        with open_source(str(f)) as source:
            assert source.name == str(f)
            assert isinstance(source.data, memoryview)
            assert bytes(source.data) == b"\x00hello\x00"

    def test_mapping_is_released_on_exit(self, tmp_path: Path) -> None:
        f = tmp_path / "t.bin"
        f.write_bytes(b"hello")
        with open_source(str(f)) as source:
            data = source.data
        with pytest.raises(ValueError, match="released"):
            bytes(data)

    def test_empty_file_is_read_not_mapped(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        with open_source(str(f)) as source:
            assert source.data == b""

    def test_stdin(self, mocker: MockerFixture) -> None:
        fake_stdin = mocker.Mock()
        fake_stdin.buffer = BytesIO(b"hello")
        mocker.patch("sys.stdin", fake_stdin)
        with open_source("-") as source:
            assert source.name == "<stdin>"
            assert source.data == b"hello"


@pytest.mark.parametrize("value", ["0", "-1"])
def test_positive_int_rejects_non_positive(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        positive_int(value)


class TestBrokenPipe:
    # Both scan paths, since the pipe closes while the file is still mapped: a
    # view the scanner kept alive would make releasing the mapping raise
    # BufferError over the BrokenPipeError
    @pytest.mark.parametrize("encoding", ["s", "l"])
    def test_main_exits_quietly_when_the_pipe_closes(
        self,
        encoding: str,
        tmp_path: Path,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # `sillystrings big.bin | head` closes stdout while we are still
        # writing. Without handling, that surfaces as a BrokenPipeError
        # traceback -- on the tool's most common invocation.
        f = tmp_path / "t.bin"
        text = "hello world\x00second string here\x00"
        f.write_bytes(text.encode("ascii" if encoding == "s" else "utf-16-le"))
        mocker.patch.object(sys, "argv", ["sillystrings", "-e", encoding, str(f)])
        mocker.patch("builtins.print", side_effect=BrokenPipeError)

        with pytest.raises(SystemExit) as exc:
            main()

        # Exits 1 like coreutils rather than surfacing a traceback. Under
        # capsys stdout has no fileno, so the devnull rebinding is suppressed
        # -- there is no real pipe to protect in that case.
        assert exc.value.code == 1
        assert capsys.readouterr().err == ""

    # -d scans a slice of the mapped file per section, so it has its own view
    # to release
    @pytest.mark.parametrize("codec", ["ascii", "utf-16-le"])
    def test_data_sections_exit_quietly_when_the_pipe_closes(
        self, codec: str, tmp_path: Path, mocker: MockerFixture, capsys: Capture
    ) -> None:
        f = tmp_path / "t.o"
        content = "hello world\x00".encode(codec)
        f.write_bytes(build_macho([("", [MachOSection("__DATA", "__data", content)])]))
        encoding = "s" if codec == "ascii" else "l"
        mocker.patch.object(sys, "argv", ["sillystrings", "-d", "-e", encoding, str(f)])
        mocker.patch("builtins.print", side_effect=BrokenPipeError)

        with pytest.raises(SystemExit) as exc:
            main()

        assert exc.value.code == 1
        assert capsys.readouterr().err == ""

    def test_broken_pipe_on_stderr_path_is_not_swallowed(
        self, mocker: MockerFixture
    ) -> None:
        # A missing file still reports normally; the handler must not turn
        # every exit into the broken-pipe path.
        mocker.patch.object(sys, "argv", ["sillystrings", "/nonexistent/file.bin"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1

    def test_main_exits_quietly_when_the_final_flush_hits_a_closed_pipe(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Output small enough to stay buffered reaches the pipe only when
        # stdout is flushed, after every print has succeeded (#56)
        f = tmp_path / "t.bin"
        f.write_bytes(b"hello world\x00")
        mocker.patch.object(sys, "argv", ["sillystrings", str(f)])
        flush = mocker.patch.object(sys.stdout, "flush", side_effect=BrokenPipeError)

        with pytest.raises(SystemExit) as exc:
            main()

        # capsys flushes the stream it captured, so only main's flush may fail
        flush.assert_called_once_with()
        flush.side_effect = None
        assert exc.value.code == 1
        assert capsys.readouterr().err == ""

    def test_reader_that_closes_before_reading(self, tmp_path: Path) -> None:
        # `sillystrings small.bin | true`: the read end is closed before the
        # process starts, so the only write -- the final flush -- always fails.
        # Unhandled, the interpreter reports it at shutdown and exits 120.
        f = tmp_path / "t.bin"
        f.write_bytes(b"hello world\x00second string\x00")
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        cmd = ["uv", "run", "sillystrings", str(f)]
        try:
            result = subprocess.run(
                cmd,
                stdout=write_fd,
                stderr=subprocess.PIPE,
                check=False,
            )
        finally:
            os.close(write_fd)
        assert result.returncode == 1
        assert result.stderr == b""
