"""What every command is given: resolved settings, output options, and a client."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from stashcli.config.settings import Settings
from stashcli.render.output import OutputOptions

if TYPE_CHECKING:
    from stashcli.client.stash import StashClient

ClientFactory = Callable[[Settings, "Runtime"], "StashClient"]


def _sleep(seconds: float) -> None:  # pragma: no cover - real waiting
    import time

    time.sleep(seconds)


@dataclass
class Runtime:
    settings: Settings
    output: OutputOptions
    make_client: ClientFactory
    assume_yes: bool = False
    verbosity: int = 0
    # Waiting is injected, so a test never does.
    sleeper: Callable[[float], None] = _sleep

    def client(self) -> "StashClient":
        return self.make_client(self.settings, self)
