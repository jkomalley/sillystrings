# tests/conftest.py
import itertools
from collections.abc import Callable
from pathlib import Path

import pytest

# encoding -> (codec for str segments, bytes per NUL character for int segments)
_LAYOUTS = {
    "s": ("ascii", 1),
    "S": ("ascii", 1),
    "l": ("utf-16-le", 2),
    "b": ("utf-16-be", 2),
    "L": ("utf-32-le", 4),
    "B": ("utf-32-be", 4),
}


def make_data(segments: list[str | int | bytes], encoding: str) -> bytes:
    codec, width = _LAYOUTS[encoding]
    result = bytearray()
    for segment in segments:
        if isinstance(segment, bytes):
            result += segment
        elif isinstance(segment, str):
            result += segment.encode(codec)
        else:
            result += b"\x00" * width * segment
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
