"""whoami, locations and storages.

Rendering and the HTTP client are imported inside the commands: `stash --help` must not
pay for rich, httpx or pydantic.
"""

import typer

from stashcli.runtime import Runtime


def whoami(ctx: typer.Context) -> None:
    """Show the identity the server verified, and its version."""
    from stashcli.render.output import emit_json
    from stashcli.render.topology import render_whoami

    runtime: Runtime = ctx.obj
    with runtime.client() as client:
        answer = client.whoami()
    if runtime.output.json:
        emit_json(answer.model_dump())
        return
    render_whoami(runtime.output.console(), answer, runtime.settings.server)


def locations(ctx: typer.Context) -> None:
    """List the locations of the cluster."""
    from stashcli.render.output import emit_json
    from stashcli.render.topology import render_locations

    runtime: Runtime = ctx.obj
    with runtime.client() as client:
        found = client.locations()
    if runtime.output.json:
        emit_json({"locations": [location.model_dump() for location in found]})
        return
    render_locations(runtime.output.console(), found)


def storages(ctx: typer.Context) -> None:
    """List the storage systems, their roles, capacity and state."""
    from stashcli.render.output import emit_json
    from stashcli.render.topology import render_storages

    runtime: Runtime = ctx.obj
    with runtime.client() as client:
        found = client.storages()
    if runtime.output.json:
        emit_json({"storages": [storage.model_dump() for storage in found]})
        return
    render_storages(runtime.output.console(), found)
