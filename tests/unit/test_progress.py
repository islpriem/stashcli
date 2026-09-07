"""How a followed transfer is shown: a bar on a terminal, lines elsewhere."""

import io

from stashcli.models.filesets import Transfer
from stashcli.render.output import OutputOptions
from stashcli.render.progress import progress_for
from tests.conftest import GIB, TRANSFERS


def transfer(bytes_done: int, state: str = "RUNNING") -> Transfer:
    return Transfer.model_validate(
        {**TRANSFERS["transfers"][0], "state": state, "bytes_done": bytes_done}
    )


def shown(*, tty: bool, polls: list[Transfer]) -> str:
    buffer = io.StringIO()
    output = OutputOptions(tty=tty, color=False, width=80)
    with progress_for(output, output.console(buffer)) as display:
        for poll in polls:
            display.update([poll])
    return buffer.getvalue()


def test_a_terminal_gets_a_bar_that_redraws_in_place() -> None:
    text = shown(tty=True, polls=[transfer(5 * GIB), transfer(35 * GIB, "SUCCEEDED")])

    first = text.split("\r")[1]  # [0] is the cursor-hide sequence
    assert "━" in text, "a bar"
    assert "\x1b[" in text, "redrawn in place, not appended"
    assert "transfer 123456 RUNNING" in first, "the first frame is already described"
    assert "14%" in first
    assert "100%" in text


def test_off_a_terminal_it_is_one_line_per_poll() -> None:
    text = shown(tty=False, polls=[transfer(5 * GIB), transfer(35 * GIB, "SUCCEEDED")])

    assert "\x1b[" not in text, "no ANSI in a job log"
    assert text.count("transfer 123456") == 2
    assert "5.0 GiB (14%) of 35.0 GiB" in text


def test_a_quiet_run_shows_no_progress_at_all() -> None:
    buffer = io.StringIO()
    output = OutputOptions(tty=False, color=False, width=80, quiet=True)
    with progress_for(output, output.console(buffer)) as display:
        display.update([transfer(5 * GIB)])

    assert buffer.getvalue() == ""
