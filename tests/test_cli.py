# tests/test_cli.py
import subprocess
from io import BytesIO
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from sillystrings.cli import build_parser, format_offset, main


def run(*args: str, data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    cmd = ["uv", "run", "sillystrings", *args]
    return subprocess.run(cmd, input=data, capture_output=True)


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


def test_version() -> None:
    result = run("-v")
    assert result.returncode == 0
    assert b"sillystrings" in result.stdout


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


Capture = pytest.CaptureFixture[str]


class TestMain:
    def test_file_input(self, tmp_path: Path, mocker: MockerFixture, capsys: Capture) -> None:
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
