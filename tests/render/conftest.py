"""Golden-file helper. A new golden is written once and then reviewed by hand."""

from collections.abc import Callable
from pathlib import Path

import pytest

GOLDEN = Path(__file__).parent / "golden"


@pytest.fixture
def assert_snapshot() -> Callable[[str, str], None]:
    def check(name: str, text: str) -> None:
        path = GOLDEN / f"{name}.txt"
        if not path.exists():
            path.write_text(text)
            pytest.fail(f"wrote a new golden file: review {path} by hand and run again")
        assert text == path.read_text(), f"output changed; review the diff against {path}"

    return check
