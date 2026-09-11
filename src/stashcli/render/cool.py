"""What cool and release say once the server has answered."""

from rich.console import Console

from stashcli.models.filesets import Transfer
from stashcli.render.output import print_block
from stashcli.sizes import format_bytes

LABEL = 18


def render_released(console: Console, transfer: Transfer, reference: str) -> None:
    console.print(f"Released {reference}")
    print_block(console, f"  {'Transfer':<{LABEL}}{transfer.id}")


def render_flushing(
    console: Console, transfer: Transfer, reference: str, target: str, *, keep: bool
) -> None:
    console.print("Queued")
    for label, value in (
        ("Transfer", str(transfer.id)),
        ("Writing out", f"{reference}  →  {target}"),
        ("Size", format_bytes(transfer.bytes_total)),
        ("Afterwards", "the fileset is kept" if keep else "the fileset is released"),
    ):
        print_block(console, f"  {label:<{LABEL}}{value}")
    console.print()
    print_block(console, f"Track with: stash status {transfer.id} --watch")
