"""warm, and the two commands that reserve space.

The server decides everything: the CLI asks for a preflight, shows what came back, then
submits. A refusal is drawn with the server's own numbers, never recomputed.
"""

from typing import TYPE_CHECKING, Annotated

import typer

from stashcli.commands.common import FilesetArgument
from stashcli.errors import NotFoundError, ServerError, UsageError
from stashcli.refs import FilesetRef, PathRef, parse_reference
from stashcli.runtime import Runtime
from stashcli.sizes import parse_size

if TYPE_CHECKING:
    from stashcli.client.stash import StashClient
    from stashcli.errors import CliError
    from stashcli.models.filesets import Fileset, Transfer

SizeOption = Annotated[str, typer.Option("--size", help="500Gi (1024-based) or 500G (1000).")]


def create(
    ctx: typer.Context,
    target: Annotated[str, typer.Argument(help="STORAGE:name, or a bare name.")],
    size: SizeOption,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Admin only.")] = None,
) -> None:
    """Create an output fileset with a reserved size."""
    from stashcli.commands.common import fileset_reference
    from stashcli.render.filesets import render_fileset_created
    from stashcli.render.output import emit_json

    runtime: Runtime = ctx.obj
    size_bytes = parse_size(size)
    with runtime.client() as client:
        reference = fileset_reference(runtime, client, target)
        created = client.create_fileset(
            storage=reference.storage, name=reference.name, size_bytes=size_bytes, user=user
        )

    if runtime.output.json:
        emit_json({"fileset": created.model_dump(mode="json")})
        return
    render_fileset_created(runtime.output.console(), created)


def resize(
    ctx: typer.Context,
    fileset: FilesetArgument,
    size: SizeOption,
    force: Annotated[
        bool, typer.Option("--force", help="Admin only: shrink below what is used.")
    ] = False,
) -> None:
    """Change what a fileset reserves."""
    from stashcli.commands.common import confirm, fileset_reference
    from stashcli.render.filesets import render_fileset_resized
    from stashcli.render.output import emit_json
    from stashcli.sizes import format_bytes

    runtime: Runtime = ctx.obj
    size_bytes = parse_size(size)
    with runtime.client() as client:
        reference = fileset_reference(runtime, client, fileset)
        current = _one(client, reference)
        if size_bytes < current.allocated_bytes:
            confirm(
                runtime,
                f"Shrink {reference} from {format_bytes(current.allocated_bytes)} "
                f"to {format_bytes(size_bytes)}?",
                hint="a smaller reservation can leave the fileset over its allocation",
            )
        resized = client.resize_fileset(current.id, size_bytes=size_bytes, force=force)

    if runtime.output.json:
        emit_json({"fileset": resized.model_dump(mode="json")})
        return
    render_fileset_resized(runtime.output.console(), resized, was=current.allocated_bytes)


def warm(
    ctx: typer.Context,
    source: Annotated[str, typer.Argument(help="STORAGE:/path to fill from.")],
    target: Annotated[str, typer.Argument(help="STORAGE:name to fill.")],
    size: Annotated[
        str | None, typer.Option("--size", help="Reserve more than the source measures.")
    ] = None,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Fill a fileset that already holds this source.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the preflight and submit nothing.")
    ] = False,
    wait: Annotated[bool, typer.Option("--wait", help="Follow it until it finishes.")] = False,
    timeout: Annotated[
        float | None, typer.Option("--timeout", help="Seconds to wait before giving up.")
    ] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Admin only.")] = None,
) -> None:
    """Fill a fileset from a source storage."""
    from stashcli.render.output import emit_json
    from stashcli.render.warm import render_preflight, render_queued

    runtime: Runtime = ctx.obj
    from_path = _source(runtime, source)
    into = _target(runtime, target)
    size_bytes = parse_size(size) if size is not None else None

    with runtime.client() as client:
        plan = client.warm_preflight(
            source_storage=from_path.storage,
            source_path=from_path.path,
            target_storage=into.storage,
            fileset=into.name,
            size_bytes=size_bytes,
            refresh=refresh,
            user=user,
        )
        allocations = client.allocations(user=user)
        console = runtime.output.console()
        if dry_run:
            if runtime.output.json:
                emit_json({"preflight": plan.model_dump(mode="json")})
                return
            render_preflight(console, plan, allocations, None)
            console.print()
            console.print("Nothing was submitted (--dry-run).")
            return

        try:
            transfer = client.warm(
                source_storage=from_path.storage,
                source_path=from_path.path,
                target_storage=into.storage,
                fileset=into.name,
                size_bytes=size_bytes,
                refresh=refresh,
                user=user,
            )
        except ServerError as refused:
            if not runtime.output.json:
                render_preflight(console, plan, allocations, refused)
            raise
        path = _path_of(client, into)

    if not runtime.output.json:
        render_preflight(console, plan, allocations, None)
        console.print()
        render_queued(console, transfer, plan, path)

    outcome = _wait_for(runtime, transfer.id, timeout) if wait else None
    if runtime.output.json:
        emit_json(
            {
                "preflight": plan.model_dump(mode="json"),
                "transfer": (outcome[0] if outcome else transfer).model_dump(mode="json"),
            }
        )
    if outcome is not None and outcome[1] is not None:
        raise outcome[1]


def _wait_for(
    runtime: Runtime, transfer_id: int, timeout: float | None
) -> tuple["Transfer", "CliError | None"]:
    """Follow the transfer that was just submitted to its end."""
    from stashcli.commands.transfers import follow_to_the_end

    with runtime.client() as client:
        followed, problem = follow_to_the_end(runtime, client, [transfer_id], timeout)
    return followed[0], problem


def _source(runtime: Runtime, text: str) -> PathRef:
    reference = parse_reference(text, default_storage=runtime.settings.storage)
    if not isinstance(reference, PathRef):
        raise UsageError(
            f"{text!r} is a fileset; warm reads from a path",
            hint="a path reference has a leading slash: STORAGE:/path",
        )
    return reference


def _target(runtime: Runtime, text: str) -> FilesetRef:
    reference = parse_reference(text, default_storage=runtime.settings.storage)
    if not isinstance(reference, FilesetRef):
        raise UsageError(
            f"{text!r} is a path; warm fills a fileset",
            hint="a fileset reference has no leading slash: STORAGE:name",
        )
    return reference


def _one(client: "StashClient", reference: FilesetRef) -> "Fileset":
    found = client.filesets(
        storage=reference.storage, name=reference.name, user=client.whoami().username
    )
    if not found:
        raise NotFoundError(f"{reference} does not exist", hint="stash fileset list")
    return found[0]


def _path_of(client: "StashClient", reference: FilesetRef) -> str:
    """The path the server made; the CLI never builds one."""
    found = client.filesets(storage=reference.storage, name=reference.name)
    return found[0].path if found else ""
