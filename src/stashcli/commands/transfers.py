"""status, queue and cancel, and the waiting the first two can do.

Several arguments are several requests: one failing does not hide the rest, and the exit
code is the worst of them.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated

import typer

from stashcli.errors import CliError, Detached, StillRunning, TransferFailed
from stashcli.runtime import Runtime
from stashcli.watch import DEFAULT_INTERVAL, Follower, is_finished

if TYPE_CHECKING:
    from stashcli.client.stash import StashClient
    from stashcli.models.filesets import Transfer

FAILED = "FAILED"


def status(
    ctx: typer.Context,
    transfer_ids: Annotated[
        list[int] | None, typer.Argument(help="Transfer ids; yours if none are given.")
    ] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Whose transfers.")] = None,
    state: Annotated[str | None, typer.Option("--state", help="Only this state.")] = None,
    show_all: Annotated[
        bool, typer.Option("--all", help="Everyone's, not just yours.")
    ] = False,
    watch: Annotated[bool, typer.Option("--watch", help="Follow until they finish.")] = False,
    interval: Annotated[
        float, typer.Option("--interval", help="Seconds between polls.")
    ] = DEFAULT_INTERVAL,
) -> None:
    """Show transfers, and optionally follow them to their end."""
    from stashcli.render.output import emit_json
    from stashcli.render.transfers import render_status

    runtime: Runtime = ctx.obj
    worst: CliError | None = None
    with runtime.client() as client:
        if watch:
            # The follower does the fetching, so an interrupt during the first poll
            # detaches like any other, and nothing is asked for twice.
            ids = transfer_ids or [
                transfer.id for transfer in _listed(client, user, state, show_all)
            ]
            transfers = _follow(runtime, client, ids, interval) if ids else []
        elif transfer_ids:
            transfers, worst = _each(client, transfer_ids)
        else:
            transfers = _listed(client, user, state, show_all)

    if runtime.output.json:
        emit_json({"transfers": [transfer.model_dump(mode="json") for transfer in transfers]})
    else:
        render_status(runtime.output.console(), transfers, tz=runtime.output.tz)
    _raise_worst(worst, transfers, watched=watch)


def queue(
    ctx: typer.Context,
    storage: Annotated[str | None, typer.Option("--storage", "-s", help="One storage.")] = None,
    route: Annotated[
        str | None, typer.Option("--route", help="One route, SOURCE->TARGET.")
    ] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="One user.")] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="At most this many.")] = None,
) -> None:
    """Show what everyone is waiting for."""
    from stashcli.render.output import emit_json
    from stashcli.render.transfers import render_queue

    runtime: Runtime = ctx.obj
    with runtime.client() as client:
        waiting = client.transfers(
            storage=storage, route=route, user=user, limit=limit
        ).transfers

    if runtime.output.json:
        emit_json({"transfers": [transfer.model_dump(mode="json") for transfer in waiting]})
        return
    render_queue(runtime.output.console(), waiting, tz=runtime.output.tz)


def cancel(
    ctx: typer.Context,
    transfer_ids: Annotated[list[int], typer.Argument(help="Transfer ids to cancel.")],
) -> None:
    """Stop transfers. What has already arrived stays where it is."""
    from stashcli.render.output import emit_json
    from stashcli.render.transfers import render_status

    runtime: Runtime = ctx.obj
    cancelled: list[Transfer] = []
    worst: CliError | None = None
    with runtime.client() as client:
        for transfer_id in transfer_ids:
            try:
                cancelled.append(client.cancel(transfer_id))
            except CliError as refusal:
                worst = _worse(worst, refusal)
                _report(transfer_id, refusal)

    if runtime.output.json:
        emit_json({"transfers": [transfer.model_dump(mode="json") for transfer in cancelled]})
    elif cancelled or worst is None:
        # Every id was refused, and each refusal was already printed: a table of
        # nothing would only add noise.
        render_status(runtime.output.console(), cancelled, tz=runtime.output.tz)
    if worst is not None:
        raise worst


def _each(
    client: "StashClient", transfer_ids: list[int]
) -> tuple[list["Transfer"], CliError | None]:
    """One request per id; a failure is reported and the rest go on."""
    found: list[Transfer] = []
    worst: CliError | None = None
    for transfer_id in transfer_ids:
        try:
            found.append(client.transfer(transfer_id))
        except CliError as failure:
            worst = _worse(worst, failure)
            _report(transfer_id, failure)
    return found, worst


def _listed(
    client: "StashClient", user: str | None, state: str | None, show_all: bool
) -> list["Transfer"]:
    subject = None if show_all else (user or client.whoami().username)
    return client.transfers(user=subject, state=state).transfers


def _follow(
    runtime: Runtime,
    client: "StashClient",
    ids: list[int],
    interval: float,
    timeout: float | None = None,
) -> list["Transfer"]:
    """Poll to the end, or detach cleanly when the user interrupts."""
    from stashcli.render.progress import progress_for

    follower = Follower(client.transfer, runtime.sleeper, interval)
    try:
        with progress_for(runtime.output, runtime.output.console()) as display:
            return follower.follow(ids, display.update, timeout)
    except KeyboardInterrupt:
        raise Detached(
            "Detached. The transfers are still running.", hint=_how_to(ids)
        ) from None


def _how_to(ids: Sequence[int]) -> str:
    listed = " ".join(str(transfer_id) for transfer_id in ids)
    return (
        f"Cancel with: stash cancel {listed}\nWatch again with: stash status {listed} --watch"
    )


def _raise_worst(worst: CliError | None, transfers: list["Transfer"], *, watched: bool) -> None:
    if worst is not None:
        raise worst
    if watched and any(transfer.state == FAILED for transfer in transfers):
        failed = [transfer for transfer in transfers if transfer.state == FAILED]
        raise TransferFailed(
            f"transfer {failed[0].id} failed"
            + (f": {failed[0].error_code}" if failed[0].error_code else "")
        )


def _worse(current: CliError | None, candidate: CliError) -> CliError:
    if current is None or candidate.exit_code > current.exit_code:
        return candidate
    return current


def _report(transfer_id: int, failure: CliError) -> None:
    import sys

    print(f"transfer {transfer_id}: {failure.message}", file=sys.stderr)


def follow_to_the_end(
    runtime: Runtime, client: "StashClient", ids: list[int], timeout: float | None = None
) -> tuple[list["Transfer"], CliError | None]:
    """What --wait does after a submission: poll to the end and judge the outcome.

    The verdict is returned, not raised, so the caller can print its one JSON object
    before the exit code is decided.
    """
    followed = _follow(runtime, client, ids, DEFAULT_INTERVAL, timeout)
    unfinished = [transfer.id for transfer in followed if not is_finished(transfer)]
    if unfinished:
        return followed, StillRunning(
            f"Timed out after {timeout:g}s. The transfers are still running.",
            hint=_how_to(unfinished),
        )
    try:
        _raise_worst(None, followed, watched=True)
    except CliError as failure:
        return followed, failure
    return followed, None
