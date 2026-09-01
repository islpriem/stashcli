"""Output options: colour and width are decided once, from the stream."""

import io

import pytest

from stashcli.render.output import DEFAULT_WIDTH, OutputOptions


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_without_a_tty_there_is_no_colour_and_the_width_is_eighty() -> None:
    options = OutputOptions.detect(
        json=False, no_color=False, quiet=False, stream=io.StringIO()
    )

    assert options.tty is False
    assert options.color is False
    assert options.width == DEFAULT_WIDTH


def test_on_a_tty_colour_is_on_unless_it_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)

    assert OutputOptions.detect(json=False, no_color=False, quiet=False, stream=Tty()).color
    assert not OutputOptions.detect(json=False, no_color=True, quiet=False, stream=Tty()).color


def test_no_color_in_the_environment_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")

    assert not OutputOptions.detect(json=False, no_color=False, quiet=False, stream=Tty()).color
