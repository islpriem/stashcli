"""stash admin: limits, reports and drain.

Every one of these is admin-only on the server; the CLI does not check, it asks and
renders the refusal if there is one.
"""

from enum import StrEnum
from typing import Annotated

import typer

from stashcli.commands.common import StorageArgument
from stashcli.errors import UsageError
from stashcli.runtime import Runtime

limit_app = typer.Typer(no_args_is_help=True, help="Per-user allocation limits.")
report_app = typer.Typer(no_args_is_help=True, help="What was moved, and who holds what.")
admin_app = typer.Typer(no_args_is_help=True, help="Administrative commands.")
admin_app.add_typer(limit_app, name="limit")
admin_app.add_typer(report_app, name="report")


class GroupBy(StrEnum):
    USER = "user"
    STORAGE = "storage"
    ROUTE = "route"
    LOCATION = "location"


@limit_app.command("set")
def limit_set(
    ctx: typer.Context,
    user: Annotated[str, typer.Argument(help="Whose limit.")],
    first: Annotated[str, typer.Argument(metavar="[STORAGE] SIZE", help="Storage, or size.")],
    second: Annotated[str | None, typer.Argument(hidden=True)] = None,
) -> None:
    """Set a per-storage or cluster-wide limit: USER [STORAGE] SIZE."""
    from stashcli.render.admin import render_limit
    from stashcli.render.output import emit_json
    from stashcli.sizes import parse_size

    runtime: Runtime = ctx.obj
    storage, size = (first, second) if second is not None else (None, first)
    with runtime.client() as client:
        limit = client.set_limit(
            user=user, storage=storage, allocation_limit_bytes=parse_size(size)
        )

    if runtime.output.json:
        emit_json({"limit": limit.model_dump(mode="json")})
        return
    render_limit(runtime.output.console(), limit)


@limit_app.command("unset")
def limit_unset(
    ctx: typer.Context,
    user: Annotated[str, typer.Argument(help="Whose limit.")],
    storage: Annotated[
        str | None, typer.Argument(help="One storage; omit for the cluster-wide limit.")
    ] = None,
) -> None:
    """Clear a limit, so the configured default applies again."""
    from stashcli.render.output import emit_json

    runtime: Runtime = ctx.obj
    with runtime.client() as client:
        client.clear_limit(user=user, storage=storage)

    where = storage or "all caches"
    if runtime.output.json:
        emit_json({"user": user, "storage_id": storage, "cleared": True})
        return
    runtime.output.console().print(f"Cleared the limit of {user} on {where}")


@report_app.command("usage")
def report_usage(
    ctx: typer.Context,
    group_by: Annotated[
        GroupBy, typer.Option("--group-by", help="What to group the numbers by.")
    ] = GroupBy.USER,
    since: Annotated[str | None, typer.Option("--since", help="Start of the window.")] = None,
    until: Annotated[str | None, typer.Option("--until", help="End of the window.")] = None,
) -> None:
    """What was transferred in a window."""
    from stashcli.render.admin import render_usage_report
    from stashcli.render.output import emit_json

    runtime: Runtime = ctx.obj
    with runtime.client() as client:
        report = client.usage_report(
            group_by=group_by.value, since=_moment(since), until=_moment(until)
        )

    if runtime.output.json:
        emit_json(report.model_dump(mode="json"))
        return
    render_usage_report(runtime.output.console(), report)


@report_app.command("allocation")
def report_allocation(ctx: typer.Context) -> None:
    """Who holds what, and whose filesets are past what they reserved."""
    from stashcli.render.admin import render_allocation_report
    from stashcli.render.output import emit_json

    runtime: Runtime = ctx.obj
    with runtime.client() as client:
        report = client.allocation_report()

    if runtime.output.json:
        emit_json(report.model_dump(mode="json"))
        return
    render_allocation_report(runtime.output.console(), report)


@admin_app.command("drain")
def drain(ctx: typer.Context, storage: StorageArgument) -> None:
    """Stop new work on a storage. What is running finishes."""
    _set_drain(ctx, storage, drained=True)


@admin_app.command("undrain")
def undrain(ctx: typer.Context, storage: StorageArgument) -> None:
    """Let a storage take work again."""
    _set_drain(ctx, storage, drained=False)


def _set_drain(ctx: typer.Context, storage: str, *, drained: bool) -> None:
    from stashcli.render.output import emit_json

    runtime: Runtime = ctx.obj
    with runtime.client() as client:
        state = client.drain(storage, drained=drained)

    if runtime.output.json:
        emit_json({"storage": state.storage, "drained": state.drained})
        return
    said = "drained: no new filesets and no new transfers" if state.drained else "taking work"
    runtime.output.console().print(f"{state.storage} is {said}")


def _moment(text: str | None) -> str | None:
    """A date or a timestamp, checked here so a typo does not reach the server."""
    if text is None:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        raise UsageError(
            f"{text!r} is not a date", hint="use 2026-08-01 or 2026-08-01T12:00:00"
        ) from None
