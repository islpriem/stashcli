"""The preflight block of a warm, and what came of it.

Every number here is one the server returned. A ✔ means the server got that far, not that
the client re-decided anything; a ✘ is drawn from the refusal it sent back.
"""

from rich.console import Console

from stashcli.errors import ServerError
from stashcli.models.filesets import Allocations, Preflight, Transfer
from stashcli.render.output import print_block
from stashcli.sizes import format_bytes

OK = "✔"
FAILED = "✘"
LABEL = 16
QUEUED_LABEL = 18

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR


def format_duration(seconds: int) -> str:
    """How long, as a person would say it: 45s, 4m, 2h30m, 1d1h."""
    if seconds <= 0:
        return "now"
    if seconds < MINUTE:
        return f"{seconds}s"
    if seconds < HOUR:
        return f"{seconds // MINUTE}m"
    if seconds < DAY:
        hours, rest = divmod(seconds, HOUR)
        return f"{hours}h{rest // MINUTE}m" if rest >= MINUTE else f"{hours}h"
    days, rest = divmod(seconds, DAY)
    return f"{days}d{rest // HOUR}h" if rest >= HOUR else f"{days}d"


def count(number: int) -> str:
    """Grouped the way the reference output writes it: 12 043."""
    return f"{number:,}".replace(",", " ")


def check(console: Console, passed: bool, label: str, detail: str) -> None:
    print_block(console, f"  {OK if passed else FAILED} {label:<{LABEL}}{detail}")


def render_preflight(
    console: Console,
    plan: Preflight,
    allocations: Allocations,
    failure: ServerError | None,
) -> None:
    scope = failure.details.get("scope") if failure is not None else None
    storage_id = plan.target.split(":", 1)[0]
    name = plan.target.split(":", 1)[1] if ":" in plan.target else plan.target

    console.print("Preflight")
    check(
        console,
        True,
        "source",
        f"{plan.source} · {format_bytes(plan.bytes_total)} · "
        f"{count(plan.file_count)} files · readable",
    )
    check(
        console,
        True,
        "name",
        f'"{name}" is a refresh of {plan.source}'
        if plan.refresh
        else f'"{name}" is free on {storage_id}',
    )
    check(
        console,
        scope != "storage",
        "allocation",
        _room(
            plan,
            failure if scope == "storage" else None,
            _storage_free(allocations, storage_id),
        )
        + f" on {storage_id}",
    )
    total = allocations.total
    check(
        console,
        scope != "total",
        "total limit",
        _room(
            plan, failure if scope == "total" else None, (total.free_bytes, total.limit_bytes)
        )
        + " across all caches",
    )


def _storage_free(allocations: Allocations, storage_id: str) -> tuple[int, int]:
    for entry in allocations.storages:
        if entry.storage_id == storage_id:
            return entry.free_bytes, entry.limit_bytes
    return (0, 0)


def _room(plan: Preflight, failure: ServerError | None, known: tuple[int, int]) -> str:
    """The server's own numbers: what it needed, and what it said was free."""
    if failure is not None:
        needed = int(failure.details.get("required_bytes", plan.allocation_bytes))
        free = int(failure.details.get("free_bytes", known[0]))
        limit = int(failure.details.get("limit_bytes", known[1]))
    else:
        needed, (free, limit) = plan.allocation_bytes, known
    return f"{format_bytes(needed)} needed · {format_bytes(free)} free of {format_bytes(limit)}"


def render_queued(console: Console, transfer: Transfer, plan: Preflight, path: str) -> None:
    source, target = plan.route.split("->", 1)
    console.print("Queued")
    for label, value in (
        ("Transfer", str(transfer.id)),
        ("Fileset", f"{plan.target}  →  {path}"),
        ("Route", f"{source} → {target}"),
        (
            "Estimate",
            f"start ~{format_duration(plan.estimated_start_seconds)} · "
            f"duration ~{format_duration(plan.estimated_duration_seconds)}  (best effort)",
        ),
    ):
        print_block(console, f"  {label:<{QUEUED_LABEL}}{value}")
    console.print()
    print_block(console, f"Track with: stash status {transfer.id} --watch")
