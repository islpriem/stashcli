"""Human rendering of filesets, their history, and what a user has reserved.

Nothing here decides anything: every number and every path comes from the server. Times
arrive UTC and are shown in the caller's zone, which each renderer takes explicitly so a
test can pin it.
"""

from collections.abc import Sequence
from datetime import datetime, tzinfo
from pathlib import PurePosixPath

from rich.console import Console
from rich.table import Table

from stashcli.models.filesets import Allocations, Fileset, Transfer
from stashcli.models.topology import Storage
from stashcli.render.output import print_block
from stashcli.sizes import ABSENT, format_bytes

TIME_FORMAT = "%Y-%m-%d %H:%M"


def table(*columns: str) -> Table:
    grid = Table(box=None, pad_edge=False, show_edge=False)
    for column in columns:
        grid.add_column(column, overflow="fold")
    return grid


def moment(value: datetime | None, tz: tzinfo) -> str:
    return value.astimezone(tz).strftime(TIME_FORMAT) if value is not None else ABSENT


def last_change(fileset: Fileset, tz: tzinfo) -> str:
    """The most recent thing that happened to it, in the server's own words."""
    events = [
        ("released", fileset.released_at),
        ("flushed", fileset.last_flushed_at),
        ("warmed", fileset.warm_finished_at),
        ("created", fileset.created_at),
    ]
    dated = [(what, when) for what, when in events if when is not None]
    what, when = max(dated, key=lambda event: event[1])
    return f"{what} {moment(when, tz)}"


def allocation_line(label: str, limit: int, allocated: int, free: int) -> str:
    return (
        f"{label:<12} {format_bytes(limit)} limit · "
        f"{format_bytes(allocated)} allocated · {format_bytes(free)} free"
    )


def shared_parent(filesets: Sequence[Fileset]) -> str | None:
    """Where the server said these filesets live, if they all live in one place."""
    parents = {str(PurePosixPath(fileset.path).parent) for fileset in filesets}
    return parents.pop() if len(parents) == 1 else None


def render_list(
    console: Console,
    filesets: Sequence[Fileset],
    allocations: Allocations,
    *,
    storage: Storage | None,
    long: bool,
    tz: tzinfo,
) -> None:
    if storage is not None:
        console.print(
            f"Storage {storage.id} ({storage.location}, {storage.tier}, {storage.driver}) "
            f"· user {allocations.user}"
        )
        for entry in allocations.storages:
            if entry.storage_id == storage.id:
                console.print(
                    allocation_line(
                        "Allocation", entry.limit_bytes, entry.allocated_bytes, entry.free_bytes
                    )
                )
    total = allocations.total
    console.print(
        allocation_line(
            "All caches", total.limit_bytes, total.allocated_bytes, total.free_bytes
        )
    )
    console.print()

    if not filesets:
        console.print("No filesets.")
        return

    # SOURCE is wide, and a listing across storages needs the room for STORAGE instead.
    with_source = storage is not None or long
    columns = ["NAME", "KIND", "STATE", "ALLOCATED", "USED"]
    if storage is None:
        columns.insert(0, "STORAGE")
    if with_source:
        columns.append("SOURCE")
    columns.append("LAST CHANGE")
    if long:
        columns.extend(["OWNER", "PATH"])
    grid = table(*columns)
    for fileset in filesets:
        row = [
            fileset.name,
            fileset.kind,
            fileset.state,
            format_bytes(fileset.allocated_bytes),
            format_bytes(fileset.used_bytes),
        ]
        if storage is None:
            row.insert(0, fileset.storage_id)
        if with_source:
            row.append(fileset.source or ABSENT)
        row.append(last_change(fileset, tz))
        if long:
            row.extend([fileset.owner_user, fileset.path])
        grid.add_row(*row)
    print_block(console, grid)

    parent = shared_parent(filesets)
    if parent is not None and not long:
        console.print()
        console.print(f"Paths under {parent}/")


def render_show(
    console: Console, fileset: Fileset, transfers: Sequence[Transfer], *, tz: tzinfo
) -> None:
    console.print(f"{fileset.reference}  ({fileset.kind}, {fileset.state})")
    fields = [
        ("Path", fileset.path),
        ("Owner", fileset.owner_user),
        ("Allocated", format_bytes(fileset.allocated_bytes)),
        ("Used", f"{format_bytes(fileset.used_bytes)} at {moment(fileset.used_bytes_at, tz)}"),
        ("Files", str(fileset.file_count) if fileset.file_count is not None else ABSENT),
    ]
    if fileset.source is not None:
        fields.append(("Source", fileset.source))
    fields.append(("Created", moment(fileset.created_at, tz)))
    if fileset.warm_finished_at is not None:
        fields.append(("Warmed", moment(fileset.warm_finished_at, tz)))
    if fileset.last_flushed_at is not None:
        fields.append(
            ("Flushed", f"{moment(fileset.last_flushed_at, tz)} to {fileset.last_flush_target}")
        )
    if fileset.released_at is not None:
        fields.append(("Released", moment(fileset.released_at, tz)))
    if fileset.over_allocation:
        fields.append(("Warning", "uses more than it reserved"))
    for label, value in fields:
        console.print(f"{label:<10} {value}")

    console.print()
    if not transfers:
        console.print("No transfers yet.")
        return
    grid = table("TRANSFER", "KIND", "STATE", "MOVED", "FINISHED")
    for transfer in transfers:
        grid.add_row(
            str(transfer.id),
            transfer.kind,
            transfer.state,
            format_bytes(transfer.bytes_done),
            moment(transfer.finished_at, tz),
        )
    print_block(console, grid)


def render_quota(
    console: Console, allocations: Allocations, storages: Sequence[Storage], *, tz: tzinfo
) -> None:
    del tz
    total = allocations.total
    console.print(f"User {allocations.user}")
    console.print(
        allocation_line(
            "All caches", total.limit_bytes, total.allocated_bytes, total.free_bytes
        )
    )
    console.print()

    if not allocations.storages:
        console.print("No cache storages.")
        return
    grid = table("STORAGE", "LIMIT", "ALLOCATED", "USED", "FREE")
    for entry in allocations.storages:
        grid.add_row(
            entry.storage_id,
            format_bytes(entry.limit_bytes),
            format_bytes(entry.allocated_bytes),
            format_bytes(entry.used_bytes),
            format_bytes(entry.free_bytes),
        )
    print_block(console, grid)

    listed = {entry.storage_id for entry in allocations.storages}
    soft = [
        storage.id
        for storage in storages
        if storage.id in listed and not storage.quota_enforced
    ]
    if soft:
        console.print()
        print_block(
            console,
            f"On {', '.join(soft)} the allocation is not enforced by the filesystem: "
            "writing past it succeeds and is reported afterwards.",
        )
