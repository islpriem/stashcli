"""The stash entry point: global options, and the only place that decides an exit code.

Command modules raise typed errors; this module turns them into a message on stderr and
its exit code. Nothing here touches the network — `stash --help` does not.
"""

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from stashcli.commands import topology
from stashcli.config.settings import Settings, default_config_paths, resolve_settings
from stashcli.errors import INTERRUPTED, CliError, UsageError
from stashcli.render.output import OutputOptions
from stashcli.runtime import Runtime

if TYPE_CHECKING:
    from stashcli.client.stash import StashClient

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    # Failures leave through main() as a message and an exit code, never as a traceback.
    pretty_exceptions_enable=False,
    help="STASH: named filesets on cache storage, warmed from a source storage.",
)
app.command("whoami")(topology.whoami)
app.command("locations")(topology.locations)
app.command("storages")(topology.storages)


def default_client(settings: Settings, runtime: Runtime) -> "StashClient":
    """The real client: MUNGE credentials over HTTP. Tests replace this seam."""
    del runtime
    from stashcli.auth.munge import MungeAuthProvider
    from stashcli.client.stash import StashClient

    return StashClient(
        settings.server,
        MungeAuthProvider(),
        timeout=settings.timeout,
        on_warning=lambda message: print(f"warning: {message}", file=sys.stderr),
    )


@app.callback(invoke_without_command=True)
def configure(
    ctx: typer.Context,
    server: Annotated[str | None, typer.Option("--server", help="Controller URL.")] = None,
    storage: Annotated[
        str | None, typer.Option("--storage", help="Default storage for bare fileset names.")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit one JSON object.")] = False,
    no_color: Annotated[
        bool, typer.Option("--no-color", help="Never colour the output.")
    ] = False,
    timeout: Annotated[
        float | None, typer.Option("--timeout", help="Request timeout in seconds.")
    ] = None,
    verbose: Annotated[int, typer.Option("-v", "--verbose", count=True, help="Say more.")] = 0,
    quiet: Annotated[bool, typer.Option("-q", "--quiet", help="Say less.")] = False,
    assume_yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask.")] = False,
    version: Annotated[bool, typer.Option("--version", help="Print the version.")] = False,
) -> None:
    if version:
        from stashcli import __version__

        typer.echo(__version__)
        raise typer.Exit
    if ctx.invoked_subcommand is None:
        raise UsageError("no command given", hint="run stash --help to see the commands")
    if ctx.obj is not None:
        return
    environment = dict(os.environ)
    settings = resolve_settings(
        server=server,
        storage=storage,
        timeout=timeout,
        env=environment,
        config_paths=default_config_paths(environment, Path.home()),
    )
    ctx.obj = Runtime(
        settings=settings,
        output=OutputOptions.detect(
            json=json_output, no_color=no_color, quiet=quiet, stream=sys.stdout
        ),
        make_client=default_client,
        assume_yes=assume_yes,
        verbosity=verbose,
    )


def report(error: CliError) -> None:
    print(f"Error: {error.message}", file=sys.stderr)
    if error.hint:
        print(error.hint, file=sys.stderr)


def main(argv: list[str] | None = None, *, runtime: Runtime | None = None) -> int:
    """Run one invocation and return its exit code."""
    try:
        result = app(args=argv, standalone_mode=False, obj=runtime)
    except CliError as error:
        report(error)
        return error.exit_code
    except (KeyboardInterrupt, EOFError, typer.Abort):
        print("Interrupted.", file=sys.stderr)
        return INTERRUPTED
    except Exception as error:
        # Typer vendors click, so its usage errors are not the classes the click package
        # exports. They all carry an exit code and know how to print themselves.
        code = getattr(error, "exit_code", None)
        show = getattr(error, "show", None)
        if code is None:
            raise
        if callable(show):
            show()
        return int(code)
    # With standalone_mode off, an early exit (--version) comes back as a return value.
    return result if isinstance(result, int) else 0


def cli() -> None:  # pragma: no cover - console script wrapper
    raise SystemExit(main())
