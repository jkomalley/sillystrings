# tests/conftest.py
import itertools
from collections.abc import Callable
from pathlib import Path

import pytest


def make_data(segments: list[str | int | bytes], encoding: str) -> bytes:
    result = bytearray()
    for segment in segments:
        if isinstance(segment, bytes):
            result += segment
        elif isinstance(segment, str):
            match encoding:
                case "s" | "S":
                    result += segment.encode("ascii")
                case "l":
                    result += segment.encode("utf-16-le")
                case "b":
                    result += segment.encode("utf-16-be")
        elif isinstance(segment, int):
            match encoding:
                case "s" | "S":
                    result += b"\x00" * segment
                case "l" | "b":
                    result += b"\x00\x00" * segment
    return bytes(result)


@pytest.fixture(scope="session")
def make_binary_file(
    tmp_path_factory: pytest.TempPathFactory,
) -> Callable[[], Path]:
    tmp_path = tmp_path_factory.mktemp("cli")
    counter = itertools.count()
    data = b"hello" + b"\x00" + b"world" + b"\x00" + b"test string"

    def _make() -> Path:
        p = tmp_path / f"sample_{next(counter)}.bin"
        p.write_bytes(data)
        return p

    return _make
