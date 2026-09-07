"""Transfer output, pinned at 80 and 120 columns."""

import io
from collections.abc import Callable
from datetime import UTC

import pytest

from stashcli.models.filesets import Transfer
from stashcli.render.output import OutputOptions
from stashcli.render.transfers import render_queue, render_status
from tests.conftest import TRANSFERS

Snapshot = Callable[[str, str], None]
WIDTHS = [80, 120]
GIB = 1024**3

FINISHED = Transfer.model_validate(TRANSFERS["transfers"][0])
RUNNING = FINISHED.model_copy(
    update={"id": 2, "state": "RUNNING", "bytes_done": 5 * GIB, "finished_at": None}
)
QUEUED = FINISHED.model_copy(
    update={
        "id": 3,
        "state": "SUBMITTED",
        "bytes_done": 0,
        "started_at": None,
        "finished_at": None,
    }
)


def rendered(width: int, draw: Callable[..., None], *args: object, **kwargs: object) -> str:
    stream = io.StringIO()
    console = OutputOptions(color=False, width=width, tty=False).console(stream)
    draw(console, *args, tz=UTC, **kwargs)
    return stream.getvalue()


class TestStatus:
    @pytest.mark.parametrize("width", WIDTHS)
    def test_a_mix_of_states(self, assert_snapshot: Snapshot, width: int) -> None:
        text = rendered(width, render_status, [QUEUED, RUNNING, FINISHED])

        assert_snapshot(f"status_{width}", text)

    def test_progress_is_shown_for_what_is_running(self) -> None:
        text = rendered(80, render_status, [RUNNING])

        assert "5.0 GiB" in text
        assert "35.0 GiB" in text, "and what it is working towards"
        assert "14%" in text

    def test_nothing_to_show_says_so(self) -> None:
        assert "No transfers." in rendered(80, render_status, [])

    def test_nothing_overflows_the_terminal(self) -> None:
        for width in WIDTHS:
            text = rendered(width, render_status, [QUEUED, RUNNING, FINISHED])

            assert all(len(line) <= width for line in text.splitlines())

    def test_a_failure_shows_its_reason(self) -> None:
        failed = RUNNING.model_copy(update={"state": "FAILED", "error_code": "no_space"})

        assert "no_space" in rendered(80, render_status, [failed])


class TestQueue:
    @pytest.mark.parametrize("width", WIDTHS)
    def test_everyones_queue(self, assert_snapshot: Snapshot, width: int) -> None:
        text = rendered(width, render_queue, [QUEUED, RUNNING])

        assert_snapshot(f"queue_{width}", text)

    def test_it_names_who_is_waiting(self) -> None:
        text = rendered(80, render_queue, [QUEUED, RUNNING])

        assert "mmustermann" in text
        assert "HOT1->LOC2HOT" in text

    def test_an_empty_queue_says_so(self) -> None:
        assert "queue is empty" in rendered(80, render_queue, []).lower()
