"""fileset list, fileset show and quota."""

from enum import StrEnum
from typing import TYPE_CHECKING, Annotated

import typer

from stashcli.errors import NotFoundError
from stashcli.runtime import Runtime

if TYPE_CHECKING:
    from stashcli.client.stash import StashClient
    from stashcli.models.topology import Storage


READY = "READY"


class Kind(StrEnum):
    """The two kinds a fileset can have; anything else is a usage error."""

    CACHED = "cached"
    OUTPUT = "output"


StorageOption = Annotated[str | None, typer.Option("--storage", "-s", help="One storage.")]
UserOption = Annotated[str | None, typer.Option("--user", "-u", help="Whose filesets.")]


def list_filesets(
    ctx: typer.Context,
    storage: StorageOption = None,
    user: UserOption = None,
    kind: Annotated[Kind | None, typer.Option("--kind", help="cached or output.")] = None,
    state: Annotated[str | None, typer.Option("--state", help="Only this state.")] = None,
    long: Annotated[
        bool, typer.Option("--long", "-l", help="Show source, owner and path.")
    ] = False,
) -> None:
    """List filesets with what they reserve and what they use."""
    from stashcli.render.filesets import render_list
    from stashcli.render.output import emit_json

    runtime: Runtime = ctx.obj
    with runtime.client() as client:
        filesets = client.filesets(
            storage=storage, user=user, kind=kind.value if kind else None, state=state
        )
        allocations = client.allocations(user=user)
        named = _storage(client, storage) if storage else None

    if runtime.output.json:
        emit_json(
            {
                "filesets": [fileset.model_dump(mode="json") for fileset in filesets],
                "allocations": allocations.model_dump(mode="json"),
            }
        )
        return
    render_list(
        runtime.output.console(),
        filesets,
        allocations,
        storage=named,
        long=long,
        tz=runtime.output.tz,
    )


def show(
    ctx: typer.Context,
    fileset: Annotated[str, typer.Argument(help="STORAGE:name, or a bare name.")],
    user: UserOption = None,
) -> None:
    """Show one fileset: where it is, what it holds, and what happened to it."""
    from stashcli.commands.common import fileset_reference
    from stashcli.render.filesets import render_show
    from stashcli.render.output import emit_json

    runtime: Runtime = ctx.obj
    with runtime.client() as client:
        reference = fileset_reference(runtime, client, fileset)
        subject = user or client.whoami().username
        found = client.filesets(storage=reference.storage, name=reference.name, user=subject)
        if not found:
            raise NotFoundError(f"{reference} does not exist", hint="stash fileset list")
        transfers = client.transfers(fileset_id=found[0].id).transfers

    if runtime.output.json:
        emit_json(
            {
                "fileset": found[0].model_dump(mode="json"),
                "transfers": [transfer.model_dump(mode="json") for transfer in transfers],
            }
        )
        return
    render_show(runtime.output.console(), found[0], transfers, tz=runtime.output.tz)


def path(
    ctx: typer.Context,
    fileset: Annotated[str, typer.Argument(help="STORAGE:name, or a bare name.")],
    user: UserOption = None,
) -> None:
    """Print where a fileset is, and nothing else.

    Exactly one line on stdout, so a job script can use it directly; exit 4 when there is
    no path worth printing, which includes a fileset that is not READY yet.
    """
    from stashcli.commands.common import fileset_reference
    from stashcli.render.output import emit_json

    runtime: Runtime = ctx.obj
    with runtime.client() as client:
        reference = fileset_reference(runtime, client, fileset)
        subject = user or client.whoami().username
        found = client.filesets(storage=reference.storage, name=reference.name, user=subject)
    if not found:
        raise NotFoundError(f"{reference} does not exist", hint="stash fileset list")
    if found[0].state != READY:
        raise NotFoundError(
            f"{reference} is {found[0].state}, not READY",
            hint="stash status shows what is still running",
        )

    if runtime.output.json:
        emit_json({"path": found[0].path, "state": found[0].state})
        return
    print(found[0].path)


def quota(ctx: typer.Context, user: UserOption = None, storage: StorageOption = None) -> None:
    """Show what a user has reserved against their limits."""
    from stashcli.render.filesets import render_quota
    from stashcli.render.output import emit_json

    runtime: Runtime = ctx.obj
    with runtime.client() as client:
        allocations = client.allocations(user=user)
        storages = client.storages()

    if storage is not None:
        allocations = allocations.model_copy(
            update={"storages": [s for s in allocations.storages if s.storage_id == storage]}
        )
    if runtime.output.json:
        emit_json({"allocations": allocations.model_dump(mode="json")})
        return
    render_quota(runtime.output.console(), allocations, storages, tz=runtime.output.tz)


def _storage(client: "StashClient", storage_id: str) -> "Storage | None":
    """The storage the header describes; the server is the only one who knows it."""
    return next((found for found in client.storages() if found.id == storage_id), None)
