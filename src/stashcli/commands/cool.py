"""cool and release: writing a fileset out, and letting it go.

What may be released without a flush is the server's rule, not this module's:
the CLI passes `--discard` on and renders whatever comes back.
"""

from typing import TYPE_CHECKING, Annotated

import typer

from stashcli.commands.common import FilesetArgument
from stashcli.errors import UsageError
from stashcli.runtime import Runtime

if TYPE_CHECKING:
    from stashcli.models.filesets import Transfer
    from stashcli.refs import PathRef

ToOption = Annotated[
    str | None, typer.Option("--to", help="STORAGE:/path to write the fileset out to.")
]


def cool(
    ctx: typer.Context,
    fileset: FilesetArgument,
    to: ToOption = None,
    keep: Annotated[
        bool, typer.Option("--keep", help="Keep the fileset after writing it out.")
    ] = False,
    discard: Annotated[
        bool, typer.Option("--discard", help="Release without writing anything out.")
    ] = False,
    wait: Annotated[
        bool, typer.Option("--wait", help="Follow the flush until it ends.")
    ] = False,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Admin only.")] = None,
) -> None:
    """Write a fileset out, release it, or both."""
    from stashcli.commands.common import confirm, fileset_reference
    from stashcli.render.cool import render_flushing
    from stashcli.render.output import emit_json

    runtime: Runtime = ctx.obj
    if to is not None and discard:
        raise UsageError(
            "--to and --discard ask for opposite things",
            hint="--to writes the data out; --discard says it is not wanted",
        )
    if keep and to is None:
        raise UsageError(
            "--keep only means something with --to",
            hint="without --to there is nothing to keep the fileset for",
        )
    target = _target(runtime, to) if to is not None else None

    with runtime.client() as client:
        reference = fileset_reference(runtime, client, fileset)
        if target is None:
            _confirm_release(runtime, str(reference))
            transfer = client.release(
                storage=reference.storage,
                fileset=reference.name,
                discard=discard,
                user=user,
            )
            _report_release(runtime, transfer, str(reference))
            return

        if not keep:
            confirm(
                runtime,
                f"Write {reference} out to {target} and release it?",
                hint="pass --keep to write it out and keep the fileset",
            )
        transfer = client.flush(
            storage=reference.storage,
            fileset=reference.name,
            target_storage=target.storage,
            target_path=target.path,
            keep=keep,
            user=user,
        )
        if runtime.output.json:
            emit_json({"transfer": transfer.model_dump(mode="json")})
        else:
            render_flushing(
                runtime.output.console(), transfer, str(reference), str(target), keep=keep
            )
        if wait:
            _wait_for(runtime, transfer.id)


def release(
    ctx: typer.Context,
    fileset: FilesetArgument,
    force: Annotated[
        bool, typer.Option("--force", help="Release even what was never written out.")
    ] = False,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Admin only.")] = None,
) -> None:
    """Delete a fileset and free what it reserved."""
    from stashcli.commands.common import fileset_reference

    runtime: Runtime = ctx.obj
    with runtime.client() as client:
        reference = fileset_reference(runtime, client, fileset)
        _confirm_release(runtime, str(reference))
        transfer = client.release(
            storage=reference.storage, fileset=reference.name, discard=force, user=user
        )
        _report_release(runtime, transfer, str(reference))


def _confirm_release(runtime: Runtime, reference: str) -> None:
    from stashcli.commands.common import confirm

    confirm(
        runtime,
        f"Release {reference}? Its contents are deleted.",
        hint="a cached fileset can be warmed again; an output fileset cannot",
    )


def _report_release(runtime: Runtime, transfer: "Transfer", reference: str) -> None:
    from stashcli.render.cool import render_released
    from stashcli.render.output import emit_json

    if runtime.output.json:
        emit_json({"transfer": transfer.model_dump(mode="json")})
        return
    render_released(runtime.output.console(), transfer, reference)


def _target(runtime: Runtime, text: str) -> "PathRef":
    from stashcli.refs import PathRef, parse_reference

    reference = parse_reference(text, default_storage=runtime.settings.storage)
    if not isinstance(reference, PathRef):
        raise UsageError(
            f"{text!r} is a fileset; --to takes a path",
            hint="a path reference has a leading slash: STORAGE:/path",
        )
    return reference


def _wait_for(runtime: Runtime, transfer_id: int) -> None:
    """Follow the flush that was just submitted to its end."""
    from stashcli.commands.transfers import follow_to_the_end

    with runtime.client() as client:
        followed, problem = follow_to_the_end(runtime, client, [transfer_id])
    del followed
    if problem is not None:
        raise problem
