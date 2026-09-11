"""How the admin commands draw what the server answered."""

from rich.console import Console

from stashcli.models.admin import AllocationReport, Limit, UsageReport
from stashcli.render.filesets import table
from stashcli.render.output import print_block
from stashcli.sizes import format_bytes


def render_limit(console: Console, limit: Limit) -> None:
    where = limit.storage_id or "all caches"
    console.print(
        f"{limit.user} may now hold {format_bytes(limit.allocation_limit_bytes)} on {where}"
    )


def render_usage_report(console: Console, report: UsageReport) -> None:
    if not report.groups:
        console.print("Nothing was transferred in that window.")
        return
    grid = table(report.group_by.upper(), "MOVED", "TRANSFERS", "OK", "WAIT p95", "THROUGHPUT")
    for group in report.groups:
        grid.add_row(
            group.key,
            format_bytes(group.bytes_transferred),
            str(group.transfers),
            f"{round(group.success_rate * 100)}%",
            _seconds(group.p95_queue_wait_seconds),
            f"{format_bytes(int(group.mean_throughput_bytes_per_s))}/s",
        )
    print_block(console, grid)


def render_allocation_report(console: Console, report: AllocationReport) -> None:
    if not report.rows:
        console.print("Nothing is allocated.")
    else:
        grid = table("USER", "STORAGE", "LIMIT", "ALLOCATED", "USED", "FILESETS")
        for row in report.rows:
            grid.add_row(
                row.user,
                row.storage_id,
                format_bytes(row.limit_bytes),
                format_bytes(row.allocated_bytes),
                format_bytes(row.used_bytes),
                str(row.filesets),
            )
        print_block(console, grid)

    if not report.offenders:
        return
    console.print()
    console.print("Past their allocation")
    offenders = table("USER", "FILESET", "ALLOCATED", "USED")
    for offender in report.offenders:
        offenders.add_row(
            offender.user,
            f"{offender.storage_id}:{offender.fileset}",
            format_bytes(offender.allocated_bytes),
            format_bytes(offender.used_bytes),
        )
    print_block(console, offenders)


def _seconds(value: float) -> str:
    return f"{round(value)}s"
