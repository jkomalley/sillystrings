import pytest

import sillystrings.encodings as encodings


class TestIsPrintableAscii:
    @pytest.mark.parametrize(
        "input_byte, encoding, include_ws, expected",
        [
            # --- encoding='s', include_ws=False ---
            # below range
            (0x00, "s", False, False),  # null
            (0x08, "s", False, False),  # backspace
            (0x09, "s", False, False),  # \t — whitespace flag off
            (0x0A, "s", False, False),  # \n — whitespace flag off
            (0x0D, "s", False, False),  # \r — whitespace flag off
            (0x0B, "s", False, False),  # \v — not in whitespace set
            (0x1F, "s", False, False),  # one below lower boundary
            # lower boundary
            (0x20, "s", False, True),  # space — first printable
            # inside range
            (0x21, "s", False, True),  # '!'
            (0x41, "s", False, True),  # 'A'
            (0x7A, "s", False, True),  # 'z'
            # upper boundary
            (0x7E, "s", False, True),  # '~' — last printable ASCII
            # above range
            (0x7F, "s", False, False),  # DEL — excluded despite sitting at 0x7F
            (0x80, "s", False, False),  # first high byte — excluded in 's' mode
            (0xFF, "s", False, False),  # max byte — excluded in 's' mode
            # --- encoding='s', include_ws=True ---
            (0x09, "s", True, True),  # \t — now included
            (0x0A, "s", True, True),  # \n — now included
            (0x0D, "s", True, True),  # \r — now included
            (0x0B, "s", True, False),  # \v — not in the whitespace set {0x09, 0x0A, 0x0D}
            (0x0C, "s", True, False),  # \f — not in the whitespace set
            (0x08, "s", True, False),  # backspace — not in the whitespace set
            (0x1F, "s", True, False),  # still below range and not a ws char
            (0x20, "s", True, True),  # space — covered by the range, not the ws check
            (0x7E, "s", True, True),  # upper boundary still works
            (0x7F, "s", True, False),  # DEL still excluded even with include_ws
            (0x80, "s", True, False),  # high byte still excluded in 's' mode
            # --- encoding='S', include_ws=False ---
            (0x1F, "S", False, False),  # below lower boundary
            (0x20, "S", False, True),  # lower boundary
            (0x7E, "S", False, True),  # top of ASCII range
            (0x7F, "S", False, False),  # DEL — excluded in all modes
            (0x80, "S", False, True),  # lower boundary of high range
            (0x81, "S", False, True),  # inside high range
            (0xA0, "S", False, True),  # mid high range
            (0xFE, "S", False, True),  # one below max
            (0xFF, "S", False, True),  # max byte — included in 'S' mode
            (0x09, "S", False, False),  # \t — whitespace flag off
            (0x0A, "S", False, False),  # \n — whitespace flag off
            # --- encoding='S', include_ws=True ---
            (0x09, "S", True, True),  # \t — included
            (0x0A, "S", True, True),  # \n — included
            (0x0D, "S", True, True),  # \r — included
            (0x0B, "S", True, False),  # \v — not in the whitespace set
            (0x7F, "S", True, False),  # DEL — still excluded even with include_ws and 'S'
            (0x80, "S", True, True),  # high byte still printable
            # --- encoding='l' (UTF-16 LE) — always False, handled by iter_chars ---
            (0x41, "l", False, False),  # 'A' — not handled by is_printable
            (0x20, "l", False, False),  # space — not handled by is_printable
            (0x09, "l", True, False),  # \t with include_ws — still False
            # --- encoding='b' (UTF-16 BE) — always False, handled by iter_chars ---
            (0x41, "b", False, False),  # 'A' — not handled by is_printable
            (0x20, "b", False, False),  # space — not handled by is_printable
            (0x09, "b", True, False),  # \t with include_ws — still False
        ],
    )
    def test_is_printable_ascii(
        self, input_byte: int, encoding: str, include_ws: bool, expected: bool
    ) -> None:
        assert encodings.is_printable_ascii(input_byte, encoding, include_ws) == expected


class TestIsPrintableUtf16:
    @pytest.mark.parametrize(
        "value, include_ws, expected",
        [
            # --- include_ws=False ---
            # below range
            (0x0000, False, False),  # null
            (0x0008, False, False),  # backspace
            (0x0009, False, False),  # \t — whitespace flag off
            (0x000A, False, False),  # \n — whitespace flag off
            (0x000D, False, False),  # \r — whitespace flag off
            (0x000B, False, False),  # \v — not in whitespace set
            (0x001F, False, False),  # one below lower boundary
            # lower boundary
            (0x0020, False, True),  # space — first printable
            # inside range
            (0x0021, False, True),  # '!'
            (0x0041, False, True),  # 'A'
            (0x007A, False, True),  # 'z'
            # upper boundary
            (0x007E, False, True),  # '~' — last printable
            # above range
            (0x007F, False, False),  # DEL — excluded
            (0x0080, False, False),  # first value above ASCII range
            (0x00FF, False, False),  # latin-1 supplement — not printable in UTF-16 mode
            (0x0100, False, False),  # beyond latin-1
            (0xD800, False, False),  # high surrogate — not printable
            (0xFFFF, False, False),  # max 16-bit value — not printable
            # --- include_ws=True ---
            (0x0009, True, True),  # \t — included
            (0x000A, True, True),  # \n — included
            (0x000D, True, True),  # \r — included
            (0x000B, True, False),  # \v — not in whitespace set {0x0009, 0x000A, 0x000D}
            (0x000C, True, False),  # \f — not in whitespace set
            (0x0008, True, False),  # backspace — not in whitespace set
            (0x001F, True, False),  # below range and not a ws char
            (0x0020, True, True),  # space — covered by range, not ws check
            (0x007E, True, True),  # upper boundary still works
            (0x007F, True, False),  # DEL — still excluded even with include_ws
            (0x0080, True, False),  # above range — still excluded
            (0xFFFF, True, False),  # max 16-bit — still excluded
        ],
    )
    def test_is_printable_utf16(self, value: int, include_ws: bool, expected: bool) -> None:
        assert encodings.is_printable_utf16(value, include_ws) == expected


class TestIterChars:
    @pytest.mark.parametrize(
        "data, encoding, include_ws, expected",
        [
            # --- encoding='s', include_ws=False ---
            # empty input
            (b"", "s", False, []),
            # single printable byte
            (b"\x41", "s", False, [(0, True)]),  # 'A'
            # single non-printable byte
            (b"\x00", "s", False, [(0, False)]),
            # boundaries
            (b"\x1f\x20\x7e\x7f", "s", False, [(0, False), (1, True), (2, True), (3, False)]),
            # mixed printable and non-printable
            (b"\x00\x41\x00", "s", False, [(0, False), (1, True), (2, False)]),
            # all printable
            (b"\x41\x42\x43", "s", False, [(0, True), (1, True), (2, True)]),
            # all non-printable
            (b"\x00\x01\x02", "s", False, [(0, False), (1, False), (2, False)]),
            # high bytes excluded in 's' mode
            (b"\x7f\x80\xff", "s", False, [(0, False), (1, False), (2, False)]),
            # offsets are correct across longer input
            (b"\x00\x00\x00\x41", "s", False, [(0, False), (1, False), (2, False), (3, True)]),
            # --- encoding='s', include_ws=True ---
            (b"\x09\x0a\x0d", "s", True, [(0, True), (1, True), (2, True)]),  # \t \n \r
            (b"\x09\x0a\x0d", "s", False, [(0, False), (1, False), (2, False)]),  # same, flag off
            (b"\x0b\x0c", "s", True, [(0, False), (1, False)]),  # \v \f — not in ws set
            (b"\x09\x41", "s", True, [(0, True), (1, True)]),  # ws char then printable
            # --- encoding='S', include_ws=False ---
            (b"", "S", False, []),
            # high bytes included
            (b"\x80\xff", "S", False, [(0, True), (1, True)]),
            # DEL still excluded
            (b"\x7f\x80", "S", False, [(0, False), (1, True)]),
            # full boundary sweep
            (
                b"\x1f\x20\x7e\x7f\x80\xff",
                "S",
                False,
                [(0, False), (1, True), (2, True), (3, False), (4, True), (5, True)],
            ),
            # --- encoding='S', include_ws=True ---
            (b"\x09\x80", "S", True, [(0, True), (1, True)]),  # ws + high byte both printable
            (b"\x09\x80", "S", False, [(0, False), (1, True)]),  # same, flag off
            # --- encoding='l' (UTF-16 LE), include_ws=False ---
            (b"", "l", False, []),
            # "hi" in UTF-16 LE
            (b"\x68\x00\x69\x00", "l", False, [(0, True), (2, True)]),
            # single non-printable pair
            (b"\x00\x00", "l", False, [(0, False)]),
            # non-ASCII codepoint — low byte in range but high byte non-zero
            (b"\x41\x01", "l", False, [(0, False)]),
            # mixed: non-printable then printable
            (b"\x00\x00\x41\x00", "l", False, [(0, False), (2, True)]),
            # odd-length data — last byte silently ignored
            (b"\x68\x00\x69", "l", False, [(0, True)]),
            # single byte — too short to form a pair, yields nothing
            (b"\x68", "l", False, []),
            # --- encoding='l' (UTF-16 LE), include_ws=True ---
            (b"\x09\x00", "l", True, [(0, True)]),  # \t in UTF-16 LE
            (b"\x09\x00", "l", False, [(0, False)]),  # same, flag off
            (b"\x0b\x00", "l", True, [(0, False)]),  # \v — not in ws set
            # --- encoding='b' (UTF-16 BE), include_ws=False ---
            (b"", "b", False, []),
            # "hi" in UTF-16 BE
            (b"\x00\x68\x00\x69", "b", False, [(0, True), (2, True)]),
            # non-printable pair
            (b"\x00\x00", "b", False, [(0, False)]),
            # non-ASCII codepoint — high byte non-zero
            (b"\x01\x41", "b", False, [(0, False)]),
            # mixed
            (b"\x00\x00\x00\x41", "b", False, [(0, False), (2, True)]),
            # odd-length data — last byte silently ignored
            (b"\x00\x68\x00", "b", False, [(0, True)]),
            # single byte — too short to form a pair, yields nothing
            (b"\x68", "b", False, []),
            # --- encoding='b' (UTF-16 BE), include_ws=True ---
            (b"\x00\x09", "b", True, [(0, True)]),  # \t in UTF-16 BE
            (b"\x00\x09", "b", False, [(0, False)]),  # same, flag off
            (b"\x00\x0b", "b", True, [(0, False)]),  # \v — not in ws set
        ],
    )
    def test_iter_chars(
        self,
        data: bytes,
        encoding: str,
        include_ws: bool,
        expected: list[tuple[int, bool]],
    ) -> None:
        result = list(encodings.iter_chars(data, encoding, include_ws))
        assert result == expected
