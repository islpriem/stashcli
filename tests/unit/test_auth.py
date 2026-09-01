"""MUNGE credentials for the CLI."""

from pathlib import Path

import pytest

from stashcli.auth.fake import FakeAuthProvider
from stashcli.auth.munge import MungeAuthProvider
from stashcli.errors import AuthUnavailable


def test_every_call_produces_a_fresh_credential() -> None:
    issued: list[int] = []

    def encoder(socket: Path | None) -> str:
        issued.append(len(issued))
        return f"cred-{len(issued)}"

    auth = MungeAuthProvider(encoder=encoder)

    assert [auth.credential(), auth.credential()] == ["cred-1", "cred-2"]


def test_the_scheme_is_the_one_the_server_expects() -> None:
    assert MungeAuthProvider().scheme == "Munge"


def test_the_configured_socket_is_passed_through() -> None:
    seen: list[Path | None] = []

    def encoder(socket: Path | None) -> str:
        seen.append(socket)
        return "cred"

    MungeAuthProvider(socket=Path("/run/munge/munge.socket.2"), encoder=encoder).credential()

    assert seen == [Path("/run/munge/munge.socket.2")]


def test_munged_being_down_is_an_authentication_failure_with_a_hint() -> None:
    def encoder(socket: Path | None) -> str:
        raise OSError("No such file or directory")

    with pytest.raises(AuthUnavailable) as excinfo:
        MungeAuthProvider(encoder=encoder).credential()

    assert excinfo.value.exit_code == 3
    assert excinfo.value.hint is not None


def test_the_fake_provider_issues_distinct_credentials() -> None:
    auth = FakeAuthProvider("cred")

    assert [auth.credential(), auth.credential()] == ["cred-1", "cred-2"]
