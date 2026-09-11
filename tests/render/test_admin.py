"""Admin and cool output, pinned at 80 and 120 columns."""

import io
from collections.abc import Callable

import pytest

from stashcli.models.admin import AllocationReport, Limit, UsageReport
from stashcli.models.filesets import Transfer
from stashcli.render.admin import render_allocation_report, render_limit, render_usage_report
from stashcli.render.cool import render_flushing, render_released
from stashcli.render.output import OutputOptions
from tests.conftest import TRANSFERS
from tests.unit.test_admin_commands import ALLOCATION_REPORT, USAGE_REPORT

Snapshot = Callable[[str, str], None]
WIDTHS = [80, 120]
GIB = 1024**3

RELEASED = Transfer.model_validate(
    {**TRANSFERS["transfers"][0], "id": 7, "kind": "release", "state": "SUCCEEDED"}
)
FLUSHING = Transfer.model_validate(
    {
        **TRANSFERS["transfers"][0],
        "id": 8,
        "kind": "flush",
        "state": "SUBMITTED",
        "route": "LOC2HOT->HOT1",
        "bytes_done": 0,
    }
)


def rendered(width: int, draw: Callable[..., None], *args: object, **kwargs: object) -> str:
    stream = io.StringIO()
    console = OutputOptions(color=False, width=width, tty=False).console(stream)
    draw(console, *args, **kwargs)
    return stream.getvalue()


class TestUsageReport:
    @pytest.mark.parametrize("width", WIDTHS)
    def test_the_numbers_a_person_reads(self, assert_snapshot: Snapshot, width: int) -> None:
        report = UsageReport.model_validate(USAGE_REPORT)

        assert_snapshot(f"report_usage_{width}", rendered(width, render_usage_report, report))

    def test_an_empty_window_says_so(self) -> None:
        report = UsageReport.model_validate({**USAGE_REPORT, "groups": []})

        assert "Nothing was transferred" in rendered(80, render_usage_report, report)


class TestAllocationReport:
    @pytest.mark.parametrize("width", WIDTHS)
    def test_holdings_and_offenders(self, assert_snapshot: Snapshot, width: int) -> None:
        report = AllocationReport.model_validate(ALLOCATION_REPORT)

        assert_snapshot(
            f"report_allocation_{width}", rendered(width, render_allocation_report, report)
        )

    def test_no_offenders_means_no_second_table(self) -> None:
        report = AllocationReport.model_validate({**ALLOCATION_REPORT, "offenders": []})

        text = rendered(80, render_allocation_report, report)

        assert "Past their allocation" not in text


class TestLimit:
    def test_it_says_who_may_hold_what_where(self) -> None:
        limit = Limit(user="jdoe", storage_id="LOC2HOT", allocation_limit_bytes=5 * GIB)

        assert rendered(80, render_limit, limit) == "jdoe may now hold 5.0 GiB on LOC2HOT\n"

    def test_no_storage_means_every_cache(self) -> None:
        limit = Limit(user="jdoe", storage_id=None, allocation_limit_bytes=5 * GIB)

        assert "all caches" in rendered(80, render_limit, limit)


class TestCool:
    @pytest.mark.parametrize("width", WIDTHS)
    def test_a_queued_flush(self, assert_snapshot: Snapshot, width: int) -> None:
        text = rendered(
            width,
            render_flushing,
            FLUSHING,
            "LOC2HOT:results",
            "HOT1:/myuser/out",
            keep=False,
        )

        assert_snapshot(f"cool_flush_{width}", text)

    def test_keeping_the_fileset_is_said_out_loud(self) -> None:
        text = rendered(
            80, render_flushing, FLUSHING, "LOC2HOT:results", "HOT1:/myuser/out", keep=True
        )

        assert "kept" in text

    def test_a_release_names_the_transfer(self) -> None:
        text = rendered(80, render_released, RELEASED, "LOC2HOT:abc")

        assert "Released LOC2HOT:abc" in text
        assert "7" in text
