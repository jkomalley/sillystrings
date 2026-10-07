# tests/test_scanner.py
import pytest

from sillystrings.encodings import Encoding
from sillystrings.scanner import scan

from .conftest import make_data


class TestScanner:
    @pytest.mark.parametrize(
        ("segments", "encoding", "min_length", "include_whitespace", "expected"),
        [
            # -----------------------------------------------------------------------
            # empty input
            # -----------------------------------------------------------------------
            ([], "s", 4, False, []),
            ([], "S", 4, False, []),
            ([], "l", 4, False, []),
            ([], "b", 4, False, []),
            ([], "L", 4, False, []),
            ([], "B", 4, False, []),
            # -----------------------------------------------------------------------
            # encoding='s' — basic cases
            # -----------------------------------------------------------------------
            # basic extraction — string surrounded by nulls
            ([1, "hello", 1], "s", 4, False, [(1, "hello")]),
            # string at offset 0
            (["hello", 1], "s", 4, False, [(0, "hello")]),
            # post-loop flush — string ends at EOF with no trailing non-printable
            ([1, "hello"], "s", 4, False, [(1, "hello")]),
            # all printable — single run, no gaps
            (["hello"], "s", 4, False, [(0, "hello")]),
            # all non-printable
            ([5], "s", 4, False, []),
            # too short — one below min_length
            ([1, "abc", 1], "s", 4, False, []),
            # exact min_length
            ([1, "abcd", 1], "s", 4, False, [(1, "abcd")]),
            # one above min_length
            ([1, "abcde", 1], "s", 4, False, [(1, "abcde")]),
            # multiple strings — both meet min_length
            (["hello", 1, "world"], "s", 4, False, [(0, "hello"), (6, "world")]),
            # multiple strings — second too short
            (["hello", 1, "hi"], "s", 4, False, [(0, "hello")]),
            # multiple strings — first too short
            (["hi", 1, "world"], "s", 4, False, [(3, "world")]),
            # three strings
            (
                ["hello", 1, "world", 1, "test1"],
                "s",
                4,
                False,
                [(0, "hello"), (6, "world"), (12, "test1")],
            ),
            # offset accuracy — large leading gap
            ([10, "hello"], "s", 4, False, [(10, "hello")]),
            # adjacent strings separated by single null
            (
                ["hello", 1, "world", 1, "fizzbuzz"],
                "s",
                4,
                False,
                [(0, "hello"), (6, "world"), (12, "fizzbuzz")],
            ),
            # min_length=1 — every printable byte is its own string
            ([1, "A", 1, "B", 1], "s", 1, False, [(1, "A"), (3, "B")]),
            # custom min_length — shorter strings now included
            (["hello", 1, "hi"], "s", 2, False, [(0, "hello"), (6, "hi")]),
            # long string
            (["the quick brown fox"], "s", 4, False, [(0, "the quick brown fox")]),
            # -----------------------------------------------------------------------
            # encoding='s' — include_whitespace
            # -----------------------------------------------------------------------
            # tab extends a run
            (["hel\tlo"], "s", 4, True, [(0, "hel\tlo")]),
            # newline extends a run
            (["hel\nlo"], "s", 4, True, [(0, "hel\nlo")]),
            # carriage return extends a run
            (["hel\rlo"], "s", 4, True, [(0, "hel\rlo")]),
            # tab extends a run when flag is off too, as in GNU
            (["hel\tlo"], "s", 4, False, [(0, "hel\tlo")]),
            # vertical tab and form feed extend a run with the flag
            (["hel\vlo"], "s", 4, True, [(0, "hel\vlo")]),
            (["hel\flo"], "s", 4, True, [(0, "hel\flo")]),
            # ... and split it without
            (["hello\vworld"], "s", 4, False, [(0, "hello"), (6, "world")]),
            (["hello\fworld"], "s", 4, False, [(0, "hello"), (6, "world")]),
            # leading tab included in run
            (["\thello"], "s", 4, True, [(0, "\thello")]),
            # tab between two strings — merges them into one run
            (["hello\tworld"], "s", 4, True, [(0, "hello\tworld")]),
            # tab between two strings — merges them when flag off too
            (["hello\tworld"], "s", 4, False, [(0, "hello\tworld")]),
            # multiple whitespace types in one run
            (["hi\t\n\v\f\r there"], "s", 4, True, [(0, "hi\t\n\v\f\r there")]),
            # -----------------------------------------------------------------------
            # encoding='S' — 8-bit extended ASCII
            # -----------------------------------------------------------------------
            # basic extraction — pure ASCII still works
            ([1, "hello", 1], "S", 4, False, [(1, "hello")]),
            # high bytes are printable — use bytes segment
            (
                [b"\x80\x81\x82\x83\x84"],
                "S",
                4,
                False,
                [(0, b"\x80\x81\x82\x83\x84".decode("latin-1"))],
            ),
            # mix of ASCII and high bytes in one run
            ([b"hel\x80\x81"], "S", 4, False, [(0, b"hel\x80\x81".decode("latin-1"))]),
            # DEL (0x7F) still excluded — breaks run between ASCII chars
            ([b"hel\x7flo"], "S", 4, False, []),
            # high bytes too short
            ([b"\x80\x81\x82"], "S", 4, False, []),
            # high bytes exact min_length
            (
                [b"\x80\x81\x82\x83"],
                "S",
                4,
                False,
                [(0, b"\x80\x81\x82\x83".decode("latin-1"))],
            ),
            # tab extends run in S mode with include_ws
            ([b"hel\x09lo"], "S", 4, True, [(0, b"hel\x09lo".decode("latin-1"))]),
            # ... and without it
            ([b"hel\x09lo"], "S", 4, False, [(0, b"hel\x09lo".decode("latin-1"))]),
            # vertical tab and form feed extend a run only with the flag
            ([b"hel\x0blo"], "S", 4, True, [(0, b"hel\x0blo".decode("latin-1"))]),
            ([b"hel\x0clo"], "S", 4, False, []),
            # -----------------------------------------------------------------------
            # encoding='l' — UTF-16 little-endian
            # -----------------------------------------------------------------------
            # basic extraction
            ([1, "hello", 1], "l", 4, False, [(2, "hello")]),
            # string at offset 0
            (["hello", 1], "l", 4, False, [(0, "hello")]),
            # post-loop flush
            ([1, "hello"], "l", 4, False, [(2, "hello")]),
            # all printable
            (["hello"], "l", 4, False, [(0, "hello")]),
            # too short
            ([1, "hi", 1], "l", 4, False, []),
            # exact min_length
            ([1, "abcd", 1], "l", 4, False, [(2, "abcd")]),
            # multiple strings
            (["hello", 1, "world"], "l", 4, False, [(0, "hello"), (12, "world")]),
            # offset accuracy — large leading gap
            ([3, "hello"], "l", 4, False, [(6, "hello")]),
            # three strings
            (
                ["hello", 1, "world", 1, "test1"],
                "l",
                4,
                False,
                [(0, "hello"), (12, "world"), (24, "test1")],
            ),
            # tab extends run
            (["hel\tlo"], "l", 4, True, [(0, "hel\tlo")]),
            # tab extends run when flag off too
            (["hel\tlo"], "l", 4, False, [(0, "hel\tlo")]),
            # vertical tab and form feed extend run only with the flag
            (["hel\vlo"], "l", 4, True, [(0, "hel\vlo")]),
            (["hel\flo"], "l", 4, True, [(0, "hel\flo")]),
            (["hello\vworld"], "l", 4, False, [(0, "hello"), (12, "world")]),
            (["hello\fworld"], "l", 4, False, [(0, "hello"), (12, "world")]),
            # tab between two strings — merges them
            (["hello\tworld"], "l", 4, True, [(0, "hello\tworld")]),
            # tab between two strings — merges them when flag off too
            (["hello\tworld"], "l", 4, False, [(0, "hello\tworld")]),
            # odd trailing byte — silently ignored, string still extracted
            (["hello", b"\x41"], "l", 4, False, [(0, "hello")]),
            # --- unaligned strings and where scanning resumes (#64) ---
            # odd start — a string need not sit on a multiple of the width
            ([b"X", "hello", 1], "l", 4, False, [(1, "hello")]),
            # a failed character resumes one byte past its start, not on the grid
            (["ab", b"\x01", "cdef", 1], "l", 4, False, [(5, "cdef")]),
            # same while extending a string already long enough
            (
                ["hello", b"\x01", "world", 1],
                "l",
                4,
                False,
                [(0, "hello"), (11, "world")],
            ),
            # min_length=1 — strings either side of a stray byte
            (["ab", b"\x01", "c", 1], "l", 1, False, [(0, "ab"), (5, "c")]),
            # trailing partial character after an unaligned string
            ([b"X", "hello", b"A"], "l", 4, False, [(1, "hello")]),
            # EOF mid-character before min_length is reached — nothing
            ([b"X", "abc", b"d"], "l", 4, False, []),
            # whitespace breaks an unaligned string only without -w
            ([b"X", "ab\ncd", 1], "l", 2, False, [(1, "ab"), (7, "cd")]),
            ([b"X", "ab\rcd", 1], "l", 2, True, [(1, "ab\rcd")]),
            # the same bytes read big-endian are "abcd" at offset 0 (see 'b')
            ([b"\x00a\x00b\x00c\x00d\x00"], "l", 4, False, [(1, "abcd")]),
            # -----------------------------------------------------------------------
            # encoding='b' — UTF-16 big-endian
            # -----------------------------------------------------------------------
            # basic extraction
            ([1, "hello", 1], "b", 4, False, [(2, "hello")]),
            # string at offset 0
            (["hello", 1], "b", 4, False, [(0, "hello")]),
            # post-loop flush
            ([1, "hello"], "b", 4, False, [(2, "hello")]),
            # all printable
            (["hello"], "b", 4, False, [(0, "hello")]),
            # too short
            ([1, "hi", 1], "b", 4, False, []),
            # exact min_length
            ([1, "abcd", 1], "b", 4, False, [(2, "abcd")]),
            # multiple strings
            (["hello", 1, "world"], "b", 4, False, [(0, "hello"), (12, "world")]),
            # offset accuracy — large leading gap
            ([3, "hello"], "b", 4, False, [(6, "hello")]),
            # three strings
            (
                ["hello", 1, "world", 1, "test1"],
                "b",
                4,
                False,
                [(0, "hello"), (12, "world"), (24, "test1")],
            ),
            # tab extends run
            (["hel\tlo"], "b", 4, True, [(0, "hel\tlo")]),
            # tab extends run when flag off too
            (["hel\tlo"], "b", 4, False, [(0, "hel\tlo")]),
            # vertical tab and form feed extend run only with the flag
            (["hel\vlo"], "b", 4, True, [(0, "hel\vlo")]),
            (["hel\flo"], "b", 4, True, [(0, "hel\flo")]),
            (["hello\vworld"], "b", 4, False, [(0, "hello"), (12, "world")]),
            (["hello\fworld"], "b", 4, False, [(0, "hello"), (12, "world")]),
            # tab between two strings — merges them
            (["hello\tworld"], "b", 4, True, [(0, "hello\tworld")]),
            # tab between two strings — merges them when flag off too
            (["hello\tworld"], "b", 4, False, [(0, "hello\tworld")]),
            # --- unaligned strings and where scanning resumes (#64) ---
            # odd start — a string need not sit on a multiple of the width
            ([b"X", "hello", 1], "b", 4, False, [(1, "hello")]),
            # a failed character resumes one byte past its start, not on the grid
            (["ab", b"\x01", "cdef", 1], "b", 4, False, [(5, "cdef")]),
            # same while extending a string already long enough
            (
                ["hello", b"\x01", "world", 1],
                "b",
                4,
                False,
                [(0, "hello"), (11, "world")],
            ),
            # min_length=1 — strings either side of a stray byte
            (["ab", b"\x01", "c", 1], "b", 1, False, [(0, "ab"), (5, "c")]),
            # trailing partial character after an unaligned string
            ([b"X", "hello", b"A"], "b", 4, False, [(1, "hello")]),
            # EOF mid-character before min_length is reached — nothing
            ([b"X", "abc", b"d"], "b", 4, False, []),
            # whitespace breaks an unaligned string only without -w
            ([b"X", "ab\ncd", 1], "b", 2, False, [(1, "ab"), (7, "cd")]),
            ([b"X", "ab\rcd", 1], "b", 2, True, [(1, "ab\rcd")]),
            # the same bytes read little-endian are "abcd" at offset 1 (see 'l')
            ([b"\x00a\x00b\x00c\x00d\x00"], "b", 4, False, [(0, "abcd")]),
            # -----------------------------------------------------------------------
            # encoding='L' — 32-bit little-endian
            # -----------------------------------------------------------------------
            # basic extraction
            ([1, "hello", 1], "L", 4, False, [(4, "hello")]),
            # string at offset 0
            (["hello", 1], "L", 4, False, [(0, "hello")]),
            # post-loop flush
            ([1, "hello"], "L", 4, False, [(4, "hello")]),
            # all printable
            (["hello"], "L", 4, False, [(0, "hello")]),
            # too short
            ([1, "hi", 1], "L", 4, False, []),
            # exact min_length
            ([1, "abcd", 1], "L", 4, False, [(4, "abcd")]),
            # multiple strings
            (["hello", 1, "world"], "L", 4, False, [(0, "hello"), (24, "world")]),
            # offset accuracy — large leading gap
            ([3, "hello"], "L", 4, False, [(12, "hello")]),
            # three strings
            (
                ["hello", 1, "world", 1, "test1"],
                "L",
                4,
                False,
                [(0, "hello"), (24, "world"), (48, "test1")],
            ),
            # tab extends run
            (["hel\tlo"], "L", 4, True, [(0, "hel\tlo")]),
            # tab extends run when flag off too
            (["hel\tlo"], "L", 4, False, [(0, "hel\tlo")]),
            # vertical tab and form feed extend run only with the flag
            (["hel\vlo"], "L", 4, True, [(0, "hel\vlo")]),
            (["hel\flo"], "L", 4, True, [(0, "hel\flo")]),
            (["hello\vworld"], "L", 4, False, [(0, "hello"), (24, "world")]),
            (["hello\fworld"], "L", 4, False, [(0, "hello"), (24, "world")]),
            # tab between two strings — merges them
            (["hello\tworld"], "L", 4, True, [(0, "hello\tworld")]),
            # tab between two strings — merges them when flag off too
            (["hello\tworld"], "L", 4, False, [(0, "hello\tworld")]),
            # trailing partial character — silently ignored, string still extracted
            (["hello", b"\x41\x00\x00"], "L", 4, False, [(0, "hello")]),
            # character beyond 16 bits breaks a run
            (
                ["hel", b"\x41\x00\x01\x00", "lo"],
                "L",
                2,
                False,
                [(0, "hel"), (16, "lo")],
            ),
            # --- unaligned strings and where scanning resumes (#64) ---
            # odd start — a string need not sit on a multiple of the width
            ([b"X", "hello", 1], "L", 4, False, [(1, "hello")]),
            ([b"XY", "hello", 1], "L", 4, False, [(2, "hello")]),
            ([b"XYZ", "hello", 1], "L", 4, False, [(3, "hello")]),
            # a failed character resumes one byte past its start, not on the grid
            (["ab", b"\x01", "cdef", 1], "L", 4, False, [(9, "cdef")]),
            # same while extending a string already long enough
            (
                ["hello", b"\x01", "world", 1],
                "L",
                4,
                False,
                [(0, "hello"), (21, "world")],
            ),
            # min_length=1 — strings either side of a stray byte
            (["ab", b"\x01", "c", 1], "L", 1, False, [(0, "ab"), (9, "c")]),
            # trailing partial character after an unaligned string
            ([b"X", "hello", b"A"], "L", 4, False, [(1, "hello")]),
            # EOF mid-character before min_length is reached — nothing
            ([b"X", "abc", b"d"], "L", 4, False, []),
            # whitespace breaks an unaligned string only without -w
            ([b"X", "ab\ncd", 1], "L", 2, False, [(1, "ab"), (13, "cd")]),
            ([b"X", "ab\rcd", 1], "L", 2, True, [(1, "ab\rcd")]),
            # -----------------------------------------------------------------------
            # encoding='B' — 32-bit big-endian
            # -----------------------------------------------------------------------
            # basic extraction
            ([1, "hello", 1], "B", 4, False, [(4, "hello")]),
            # string at offset 0
            (["hello", 1], "B", 4, False, [(0, "hello")]),
            # post-loop flush
            ([1, "hello"], "B", 4, False, [(4, "hello")]),
            # all printable
            (["hello"], "B", 4, False, [(0, "hello")]),
            # too short
            ([1, "hi", 1], "B", 4, False, []),
            # exact min_length
            ([1, "abcd", 1], "B", 4, False, [(4, "abcd")]),
            # multiple strings
            (["hello", 1, "world"], "B", 4, False, [(0, "hello"), (24, "world")]),
            # offset accuracy — large leading gap
            ([3, "hello"], "B", 4, False, [(12, "hello")]),
            # three strings
            (
                ["hello", 1, "world", 1, "test1"],
                "B",
                4,
                False,
                [(0, "hello"), (24, "world"), (48, "test1")],
            ),
            # tab extends run
            (["hel\tlo"], "B", 4, True, [(0, "hel\tlo")]),
            # tab extends run when flag off too
            (["hel\tlo"], "B", 4, False, [(0, "hel\tlo")]),
            # vertical tab and form feed extend run only with the flag
            (["hel\vlo"], "B", 4, True, [(0, "hel\vlo")]),
            (["hel\flo"], "B", 4, True, [(0, "hel\flo")]),
            (["hello\vworld"], "B", 4, False, [(0, "hello"), (24, "world")]),
            (["hello\fworld"], "B", 4, False, [(0, "hello"), (24, "world")]),
            # tab between two strings — merges them
            (["hello\tworld"], "B", 4, True, [(0, "hello\tworld")]),
            # tab between two strings — merges them when flag off too
            (["hello\tworld"], "B", 4, False, [(0, "hello\tworld")]),
            # --- unaligned strings and where scanning resumes (#64) ---
            # odd start — a string need not sit on a multiple of the width
            ([b"X", "hello", 1], "B", 4, False, [(1, "hello")]),
            ([b"XY", "hello", 1], "B", 4, False, [(2, "hello")]),
            ([b"XYZ", "hello", 1], "B", 4, False, [(3, "hello")]),
            # a failed character resumes one byte past its start, not on the grid
            (["ab", b"\x01", "cdef", 1], "B", 4, False, [(9, "cdef")]),
            # same while extending a string already long enough
            (
                ["hello", b"\x01", "world", 1],
                "B",
                4,
                False,
                [(0, "hello"), (21, "world")],
            ),
            # min_length=1 — strings either side of a stray byte
            (["ab", b"\x01", "c", 1], "B", 1, False, [(0, "ab"), (9, "c")]),
            # trailing partial character after an unaligned string
            ([b"X", "hello", b"A"], "B", 4, False, [(1, "hello")]),
            # EOF mid-character before min_length is reached — nothing
            ([b"X", "abc", b"d"], "B", 4, False, []),
            # whitespace breaks an unaligned string only without -w
            ([b"X", "ab\ncd", 1], "B", 2, False, [(1, "ab"), (13, "cd")]),
            ([b"X", "ab\rcd", 1], "B", 2, True, [(1, "ab\rcd")]),
        ],
    )
    def test_scan(
        self,
        segments: list[str | int | bytes],
        encoding: Encoding,
        min_length: int,
        include_whitespace: bool,
        expected: list[tuple[int, str]],
    ) -> None:
        data = make_data(segments, encoding)
        result = list(
            scan(
                data,
                encoding=encoding,
                min_length=min_length,
                include_whitespace=include_whitespace,
            )
        )
        assert result == expected

    def test_scan_rejects_unknown_encoding(self) -> None:
        # scan is a generator, so the error only surfaces on consumption
        with pytest.raises(ValueError, match="unsupported encoding: z"):
            list(scan(b"hello", encoding="z"))  # ty: ignore[invalid-argument-type]
