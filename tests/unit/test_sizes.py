"""Size input and IEC output."""

import pytest

from stashcli.errors import UsageError
from stashcli.sizes import format_bytes, parse_size


class TestParsing:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("500Gi", 500 * 1024**3),
            ("2Ti", 2 * 1024**4),
            ("1024", 1024),
            ("100GiB", 100 * 1024**3),
        ],
    )
    def test_iec_input(self, text: str, expected: int) -> None:
        assert parse_size(text) == expected

    def test_500G_and_500Gi_are_different(self) -> None:
        assert parse_size("500G") == 500 * 1000**3
        assert parse_size("500Gi") == 500 * 1024**3

    @pytest.mark.parametrize("text", ["", "big", "-5Gi", "1.5Gi", "500Gb"])
    def test_malformed_sizes_are_usage_errors(self, text: str) -> None:
        with pytest.raises(UsageError):
            parse_size(text)


class TestFormatting:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0, "0 B"),
            (512, "512 B"),
            (1024, "1.0 KiB"),
            (22548578304, "21.0 GiB"),
            (107374182400, "100.0 GiB"),
            (500 * 1024**4, "500.0 TiB"),
            (2 * 1024**6, "2.0 EiB"),
        ],
    )
    def test_output_is_iec_with_one_decimal(self, value: int, expected: str) -> None:
        assert format_bytes(value) == expected

    def test_nothing_is_rendered_for_an_absent_size(self) -> None:
        assert format_bytes(None) == "—"
