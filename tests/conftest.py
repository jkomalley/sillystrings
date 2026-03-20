# tests/conftest.py
from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def make_binary(tmp_path: Path) -> Callable[list[bytes], Path]:
    def _make(segments: list[bytes]) -> Path:
        binary_path = tmp_path / "test.bin"
        binary_path.write_bytes(b"".join(segments))
        return binary_path

    return _make
