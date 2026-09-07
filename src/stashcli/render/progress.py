"""Following a transfer: a bar on a terminal, a line per poll anywhere else.

Job scripts get the lines. Nothing here writes ANSI when the output is not a terminal,
and `--quiet` shows nothing at all.
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Protocol

from stashcli.render.output import OutputOptions, print_block
from stashcli.sizes import format_bytes

if TYPE_CHECKING:
    from rich.console import Console
    from rich.progress import Progress, TaskID

    from stashcli.models.filesets import Transfer


class Display(Protocol):
    def update(self, transfers: Sequence["Transfer"]) -> None: ...


class Silent:
    def update(self, transfers: Sequence["Transfer"]) -> None:
        del transfers


class Lines:
    """What a job log gets: one line per transfer per poll, no cursor tricks."""

    def __init__(self, console: "Console") -> None:
        self._console = console

    def update(self, transfers: Sequence["Transfer"]) -> None:
        from stashcli.render.transfers import outcome, share

        for transfer in transfers:
            print_block(
                self._console,
                f"transfer {transfer.id}: {outcome(transfer)} · {share(transfer)} "
                f"of {format_bytes(transfer.bytes_total)}",
            )


class Bars:
    """One bar per transfer, redrawn in place while a person watches."""

    def __init__(self, progress: "Progress") -> None:
        self._progress = progress
        self._tasks: dict[int, TaskID] = {}

    def update(self, transfers: Sequence["Transfer"]) -> None:
        from stashcli.render.transfers import outcome

        for transfer in transfers:
            described = f"transfer {transfer.id} {outcome(transfer)}"
            moved = (
                f"{format_bytes(transfer.bytes_done)} of {format_bytes(transfer.bytes_total)}"
            )
            task = self._tasks.get(transfer.id)
            if task is None:
                # Described at creation: add_task draws a frame of its own.
                self._tasks[transfer.id] = self._progress.add_task(
                    described,
                    total=transfer.bytes_total or None,
                    completed=transfer.bytes_done,
                    moved=moved,
                )
                continue
            self._progress.update(
                task, completed=transfer.bytes_done, description=described, moved=moved
            )
        self._progress.refresh()


@contextmanager
def progress_for(output: OutputOptions, console: "Console") -> Iterator[Display]:
    """The display that suits where the output is going."""
    if output.quiet or output.json:
        yield Silent()
        return
    if not output.tty:
        yield Lines(console)
        return
    from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn

    progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("{task.fields[moved]}"),
        console=console,
        auto_refresh=False,
    )
    with progress:
        yield Bars(progress)
