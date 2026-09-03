"""How output is produced: a Rich console for humans, one JSON object for machines.

Every renderer takes an explicit width and TTY flag, so what a job script sees is exactly
what a test asserts.
"""

import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from rich.console import Console

SCHEMA_VERSION = 1
DEFAULT_WIDTH = 80
LOCAL = datetime.now().astimezone().tzinfo or UTC


@dataclass(frozen=True, slots=True)
class OutputOptions:
    json: bool = False
    color: bool = True
    width: int = DEFAULT_WIDTH
    tty: bool = False
    quiet: bool = False
    # Timestamps arrive UTC and are shown where the user is; tests pin it.
    tz: tzinfo = LOCAL

    @classmethod
    def detect(
        cls, *, json: bool, no_color: bool, quiet: bool, stream: TextIO
    ) -> "OutputOptions":
        tty = stream.isatty()
        return cls(
            json=json,
            color=tty and not no_color and not os.environ.get("NO_COLOR"),
            width=shutil.get_terminal_size((DEFAULT_WIDTH, 24)).columns
            if tty
            else DEFAULT_WIDTH,
            tty=tty,
            quiet=quiet,
        )

    def console(self, stream: TextIO | None = None) -> "Console":
        from rich.console import Console

        return Console(
            file=stream or sys.stdout,
            width=self.width,
            force_terminal=self.tty or None,
            no_color=not self.color,
            highlight=False,
            soft_wrap=False,
        )


def print_block(console: "Console", renderable: object) -> None:
    """Print a Rich renderable without the padding it puts after the last column."""
    with console.capture() as captured:
        console.print(renderable)
    console.file.write("".join(f"{line.rstrip()}\n" for line in captured.get().splitlines()))


def emit_json(payload: dict[str, Any], stream: TextIO | None = None) -> None:
    """One object per invocation, with the server's field names and raw bytes."""
    print(json.dumps({"schema_version": SCHEMA_VERSION, **payload}), file=stream or sys.stdout)
