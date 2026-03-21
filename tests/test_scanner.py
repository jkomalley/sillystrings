# tests/test_scanner.py
from typing import Literal

import pytest

from sillystrings.scanner import scan

from .conftest import make_data


class TestScanner:
    @pytest.mark.parametrize(
        "segments, encoding, min_length, include_whitespace, expected",
        [
            # -----------------------------------------------------------------------
            # empty input
            # -----------------------------------------------------------------------
            ([], "s", 4, False, []),
            ([], "S", 4, False, []),
            ([], "l", 4, False, []),
            ([], "b", 4, False, []),
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
            # tab breaks a run when flag is off
            (["hel\tlo"], "s", 4, False, []),
            # leading tab included in run
            (["\thello"], "s", 4, True, [(0, "\thello")]),
            # tab between two strings — merges them into one run
            (["hello\tworld"], "s", 4, True, [(0, "hello\tworld")]),
            # tab between two strings — splits them when flag off
            (["hello\tworld"], "s", 4, False, [(0, "hello"), (6, "world")]),
            # multiple whitespace types in one run
            (["hi\t\n\r there"], "s", 4, True, [(0, "hi\t\n\r there")]),
            # -----------------------------------------------------------------------
            # encoding='S' — 8-bit extended ASCII
            # -----------------------------------------------------------------------
            # basic extraction — pure ASCII still works
            ([1, "hello", 1], "S", 4, False, [(1, "hello")]),
            # high bytes are printable — use bytes segment
            ([b"\x80\x81\x82\x83"], "S", 4, False, [(0, b"\x80\x81\x82\x83".decode("latin-1"))]),
            # mix of ASCII and high bytes in one run
            ([b"hel\x80\x81"], "S", 4, False, [(0, b"hel\x80\x81".decode("latin-1"))]),
            # DEL (0x7F) still excluded — breaks run between ASCII chars
            ([b"hel\x7flo"], "S", 4, False, []),
            # high bytes too short
            ([b"\x80\x81\x82"], "S", 4, False, []),
            # high bytes exact min_length
            ([b"\x80\x81\x82\x83"], "S", 4, False, [(0, b"\x80\x81\x82\x83".decode("latin-1"))]),
            # tab extends run in S mode with include_ws
            ([b"hel\x09lo"], "S", 4, True, [(0, b"hel\x09lo".decode("latin-1"))]),
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
            # tab breaks run when flag off
            (["hel\tlo"], "l", 4, False, []),
            # tab between two strings — merges them
            (["hello\tworld"], "l", 4, True, [(0, "hello\tworld")]),
            # tab between two strings — splits them
            (["hello\tworld"], "l", 4, False, [(0, "hello"), (12, "world")]),
            # odd trailing byte — silently ignored, string still extracted
            (["hello"], "l", 4, False, [(0, "hello")]),  # make_data won't add odd bytes,
            # test odd bytes separately with raw bytes
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
            # tab breaks run when flag off
            (["hel\tlo"], "b", 4, False, []),
            # tab between two strings — merges them
            (["hello\tworld"], "b", 4, True, [(0, "hello\tworld")]),
            # tab between two strings — splits them
            (["hello\tworld"], "b", 4, False, [(0, "hello"), (12, "world")]),
        ],
    )
    def test_scan(
        self,
        segments: list[str | int | bytes],
        encoding: Literal["s", "S", "l", "b"],
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
