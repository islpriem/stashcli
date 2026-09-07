"""The preflight block, pinned at 80 and 120 columns."""

import io
from collections.abc import Callable

import pytest

from stashcli.errors import ServerError
from stashcli.models.filesets import Allocations, Preflight, Transfer
from stashcli.render.output import OutputOptions
from stashcli.render.warm import format_duration, render_preflight, render_queued
from tests.conftest import ALLOCATIONS, PREFLIGHT, TRANSFERS

Snapshot = Callable[[str, str], None]
WIDTHS = [80, 120]
GIB = 1024**3

PLAN = Preflight.model_validate(PREFLIGHT)
ALLOCATION = Allocations.model_validate(ALLOCATIONS)
QUEUED = Transfer.model_validate({**TRANSFERS["transfers"][0], "state": "ASSIGNED"})


def rendered(width: int, draw: Callable[..., None], *args: object, **kwargs: object) -> str:
    stream = io.StringIO()
    console = OutputOptions(color=False, width=width, tty=False).console(stream)
    draw(console, *args, **kwargs)
    return stream.getvalue()


class TestDuration:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [(0, "now"), (45, "45s"), (240, "4m"), (9000, "2h30m"), (3600, "1h"), (90061, "1d1h")],
    )
    def test_a_duration_reads_as_a_person_would_say_it(
        self, seconds: int, expected: str
    ) -> None:
        assert format_duration(seconds) == expected


class TestPreflight:
    @pytest.mark.parametrize("width", WIDTHS)
    def test_a_warm_that_the_server_accepted(
        self, assert_snapshot: Snapshot, width: int
    ) -> None:
        text = rendered(width, render_preflight, PLAN, ALLOCATION, None)

        assert_snapshot(f"warm_preflight_{width}", text)

    def test_the_numbers_are_the_servers_own(self) -> None:
        text = rendered(80, render_preflight, PLAN, ALLOCATION, None)

        assert "20.0 GiB" in text, "the measured source"
        assert "12043 files" in text or "12 043 files" in text
        assert "21.0 GiB needed" in text, "the allocation the server decided"
        assert "90.0 GiB free of 200.0 GiB" in text, "on that storage"
        assert "140.0 GiB free of 250.0 GiB" in text, "across all caches"

    def test_a_refresh_says_so_instead_of_calling_the_name_free(self) -> None:
        text = rendered(
            80, render_preflight, PLAN.model_copy(update={"refresh": True}), ALLOCATION, None
        )

        assert "refresh" in text
        assert "is free" not in text

    @pytest.mark.parametrize("width", WIDTHS)
    def test_a_refusal_marks_the_check_that_failed(
        self, assert_snapshot: Snapshot, width: int
    ) -> None:
        refusal = ServerError(
            code="ALLOCATION_LIMIT_EXCEEDED",
            message="allocation limit exceeded on LOC2HOT",
            details={
                "required_bytes": 315 * GIB,
                "free_bytes": 90 * GIB,
                "limit_bytes": 200 * GIB,
                "scope": "storage",
                "storage": "LOC2HOT",
            },
        )

        text = rendered(width, render_preflight, PLAN, ALLOCATION, refusal)

        assert "✘" in text
        assert_snapshot(f"warm_preflight_refused_{width}", text)

    def test_a_refusal_of_the_cluster_wide_limit_marks_that_line(self) -> None:
        refusal = ServerError(
            code="TOTAL_ALLOCATION_LIMIT_EXCEEDED",
            message="no room",
            details={
                "required_bytes": 315 * GIB,
                "free_bytes": 10 * GIB,
                "limit_bytes": 250 * GIB,
                "scope": "total",
            },
        )

        lines = rendered(80, render_preflight, PLAN, ALLOCATION, refusal).splitlines()

        assert next(line for line in lines if "✘" in line).strip().startswith("✘ total limit")

    def test_a_refusal_the_preflight_has_no_line_for_marks_nothing(self) -> None:
        refusal = ServerError(code="STORAGE_DRAINED", message="drained", details={})

        assert "✘" not in rendered(80, render_preflight, PLAN, ALLOCATION, refusal)

    def test_a_storage_the_allocations_do_not_mention_shows_nothing_invented(self) -> None:
        elsewhere = PLAN.model_copy(update={"target": "OTHER:mydir"})

        text = rendered(80, render_preflight, elsewhere, ALLOCATION, None)

        assert "0 B free of 0 B on OTHER" in text


class TestQueued:
    @pytest.mark.parametrize("width", WIDTHS)
    def test_what_was_queued(self, assert_snapshot: Snapshot, width: int) -> None:
        text = rendered(
            width,
            render_queued,
            QUEUED,
            PLAN,
            "/cache/loc2/mmustermann/mydir",
        )

        assert_snapshot(f"warm_queued_{width}", text)

    def test_it_says_how_to_follow_the_transfer(self) -> None:
        text = rendered(80, render_queued, QUEUED, PLAN, "/cache/loc2/mmustermann/mydir")

        assert "stash status 123456" in text
        assert "best effort" in text
