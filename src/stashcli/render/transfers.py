"""Human rendering of transfers: the queue, their status, and how far they have got."""

from collections.abc import Sequence
from datetime import tzinfo

from rich.console import Console

from stashcli.models.filesets import Transfer
from stashcli.render.filesets import moment, table
from stashcli.render.output import print_block
from stashcli.sizes import ABSENT, format_bytes


def share(transfer: Transfer) -> str:
    """How far it has got, as the server counted it."""
    if not transfer.bytes_total:
        return ABSENT
    percent = transfer.bytes_done * 100 // transfer.bytes_total
    return f"{format_bytes(transfer.bytes_done)} ({percent}%)"


def outcome(transfer: Transfer) -> str:
    """The state, and why, when there is a why. A column of dashes helps nobody."""
    return (
        f"{transfer.state} ({transfer.error_code})" if transfer.error_code else transfer.state
    )


def render_status(console: Console, transfers: Sequence[Transfer], *, tz: tzinfo) -> None:
    if not transfers:
        console.print("No transfers.")
        return
    grid = table("ID", "KIND", "STATE", "SIZE", "MOVED", "SUBMITTED")
    for transfer in transfers:
        grid.add_row(
            str(transfer.id),
            transfer.kind,
            outcome(transfer),
            format_bytes(transfer.bytes_total),
            share(transfer),
            moment(transfer.submitted_at, tz),
        )
    print_block(console, grid)


def render_queue(console: Console, transfers: Sequence[Transfer], *, tz: tzinfo) -> None:
    if not transfers:
        console.print("The queue is empty.")
        return
    grid = table("ID", "USER", "KIND", "STATE", "ROUTE", "SIZE", "SUBMITTED")
    for transfer in transfers:
        grid.add_row(
            str(transfer.id),
            transfer.user,
            transfer.kind,
            transfer.state,
            transfer.route,
            format_bytes(transfer.bytes_total),
            moment(transfer.submitted_at, tz),
        )
    print_block(console, grid)
