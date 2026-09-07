"""Following transfers until they finish.

The clock and the sleeper are handed in, so a test never waits and a job script never
polls faster than it was told to.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stashcli.models.filesets import Transfer

TERMINAL = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})
DEFAULT_INTERVAL = 5.0

Fetch = Callable[[int], "Transfer"]
OnUpdate = Callable[[Sequence["Transfer"]], None]


def is_finished(transfer: "Transfer") -> bool:
    return transfer.state in TERMINAL


@dataclass(frozen=True, slots=True)
class Follower:
    fetch: Fetch
    sleeper: Callable[[float], None]
    interval: float = DEFAULT_INTERVAL
    now: Callable[[], float] = field(default=time.monotonic)

    def follow(
        self,
        transfer_ids: Sequence[int],
        on_update: OnUpdate,
        timeout: float | None = None,
    ) -> list["Transfer"]:
        """Poll until every transfer is finished, or until the deadline, showing each round.

        Returning short of a terminal state is how the caller learns it timed out.
        """
        wanted = list(transfer_ids)
        started = self.now()
        latest = [self.fetch(transfer_id) for transfer_id in wanted]
        on_update(latest)
        while not all(is_finished(transfer) for transfer in latest):
            if timeout is not None and self.now() - started >= timeout:
                return latest
            self.sleeper(self.interval)
            # Polled by the id that was asked for, never by the one echoed back.
            latest = [
                transfer if is_finished(transfer) else self.fetch(transfer_id)
                for transfer_id, transfer in zip(wanted, latest, strict=True)
            ]
            on_update(latest)
        return latest
