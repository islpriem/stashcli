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


class TestTextTheServerChose:
    """Paths and messages come from the server; none of it is markup."""

    def test_a_path_with_brackets_is_printed_as_it_is(self) -> None:
        stream = io.StringIO()
        console = OutputOptions(color=False, width=80, tty=False).console(stream)

        console.print("/data/[test]/x")

        assert stream.getvalue() == "/data/[test]/x\n"

    def test_a_bracket_in_a_table_cell_survives_too(self) -> None:
        from stashcli.render.filesets import table
        from stashcli.render.output import print_block

        stream = io.StringIO()
        console = OutputOptions(color=False, width=80, tty=False).console(stream)
        grid = table("PATH")
        grid.add_row("/data/[bold]x[/bold]")

        print_block(console, grid)

        assert "[bold]x[/bold]" in stream.getvalue()
