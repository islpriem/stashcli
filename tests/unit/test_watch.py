"""Following transfers to their end, without waiting for real time."""

import pytest

from stashcli.models.filesets import Transfer
from stashcli.watch import Follower, is_finished
from tests.conftest import TRANSFERS

RUNNING = Transfer.model_validate({**TRANSFERS["transfers"][0], "state": "RUNNING"})


def at(state: str, bytes_done: int = 0, transfer_id: int = 123456) -> Transfer:
    return RUNNING.model_copy(
        update={"state": state, "bytes_done": bytes_done, "id": transfer_id}
    )


class Server:
    """Hands out the states a transfer goes through, one poll at a time."""

    def __init__(self, *states: Transfer) -> None:
        self.answers = list(states)
        self.polls = 0

    def fetch(self, transfer_id: int) -> Transfer:
        self.polls += 1
        return self.answers[min(self.polls - 1, len(self.answers) - 1)]


@pytest.mark.parametrize("state", ["SUCCEEDED", "FAILED", "CANCELLED"])
def test_a_terminal_state_is_recognised(state: str) -> None:
    assert is_finished(at(state))


@pytest.mark.parametrize("state", ["SUBMITTED", "ASSIGNED", "RUNNING"])
def test_a_transfer_still_going_is_not(state: str) -> None:
    assert not is_finished(at(state))


def test_it_polls_until_the_transfer_finishes() -> None:
    server = Server(at("RUNNING", 1), at("RUNNING", 2), at("SUCCEEDED", 3))
    slept: list[float] = []
    seen: list[str] = []

    result = Follower(server.fetch, slept.append, interval=5.0).follow(
        [123456], lambda transfers: seen.append(transfers[0].state)
    )

    assert seen == ["RUNNING", "RUNNING", "SUCCEEDED"]
    assert result[0].bytes_done == 3
    assert slept == [5.0, 5.0], "it waited the interval it was given, twice"


def test_a_transfer_that_is_already_finished_is_not_polled_again() -> None:
    server = Server(at("SUCCEEDED"))
    slept: list[float] = []

    Follower(server.fetch, slept.append).follow([123456], lambda transfers: None)

    assert server.polls == 1
    assert slept == []


def test_several_transfers_are_followed_together() -> None:
    answers = {1: [at("RUNNING", 1, 1), at("SUCCEEDED", 9, 1)], 2: [at("SUCCEEDED", 5, 2)]}
    polls: dict[int, int] = {1: 0, 2: 0}

    def fetch(transfer_id: int) -> Transfer:
        polls[transfer_id] += 1
        answers_for = answers[transfer_id]
        return answers_for[min(polls[transfer_id] - 1, len(answers_for) - 1)]

    result = Follower(fetch, lambda seconds: None).follow([1, 2], lambda transfers: None)

    assert [transfer.state for transfer in result] == ["SUCCEEDED", "SUCCEEDED"]
    assert polls[2] == 1, "the one that was already done was left alone"


def test_the_interrupt_is_the_callers_to_handle() -> None:
    """Ctrl-C detaches; the follower does not decide what that means."""

    def fetch(transfer_id: int) -> Transfer:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        Follower(fetch, lambda seconds: None).follow([1], lambda transfers: None)


class TestGivingUp:
    def test_it_stops_at_the_deadline_and_returns_what_it_last_saw(self) -> None:
        server = Server(at("RUNNING"))
        elapsed = iter([0.0, 6.0, 12.0])
        follower = Follower(
            fetch=server.fetch,
            sleeper=lambda seconds: None,
            interval=5.0,
            now=lambda: next(elapsed),
        )

        seen = follower.follow([123456], lambda transfers: None, timeout=10.0)

        assert [transfer.state for transfer in seen] == ["RUNNING"]
        assert server.polls == 2, "one poll, one more after the first sleep, then it gives up"

    def test_no_deadline_polls_to_the_end(self) -> None:
        server = Server(at("RUNNING"), at("RUNNING"), at("SUCCEEDED"))
        follower = Follower(fetch=server.fetch, sleeper=lambda seconds: None, interval=5.0)

        seen = follower.follow([123456], lambda transfers: None)

        assert [transfer.state for transfer in seen] == ["SUCCEEDED"]
