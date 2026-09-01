"""Server error code to exit code, and the CLI's own failures."""

import pytest

from stashcli.errors import (
    AuthUnavailable,
    CliError,
    ServerError,
    TransportError,
    UsageError,
    exit_code_for,
)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("INTERNAL", 1),
        ("SOMETHING_NEW", 1),
        ("INVALID_REQUEST", 2),
        ("UNAUTHENTICATED", 3),
        ("NOT_FOUND", 4),
        ("PATH_NOT_FOUND", 4),
        ("FILESET_NOT_READY", 4),
        ("ALLOCATION_LIMIT_EXCEEDED", 5),
        ("TOTAL_ALLOCATION_LIMIT_EXCEEDED", 5),
        ("STORAGE_FULL", 5),
        ("OVER_ALLOCATION", 5),
        ("TOO_MANY_FILESETS", 5),
        ("TOO_MANY_QUEUED", 5),
        ("CONFLICT", 6),
        ("FILESET_EXISTS", 6),
        ("SOURCE_MISMATCH", 6),
        ("FORBIDDEN", 6),
        ("PERMISSION_DENIED", 6),
        ("INVALID_NAME", 6),
        ("INVALID_PATH", 6),
        ("NOT_A_SOURCE_STORAGE", 6),
        ("NOT_A_CACHE_STORAGE", 6),
        ("FLUSH_TARGET_REQUIRED", 6),
        ("DAEMON_UNAVAILABLE", 7),
        ("STORAGE_DRAINED", 7),
        ("CONFIG_STALE", 7),
    ],
)
def test_every_server_code_maps_to_its_exit_code(code: str, expected: int) -> None:
    assert exit_code_for(code) == expected


def test_an_unknown_code_keeps_the_server_message_verbatim() -> None:
    error = ServerError(code="SOMETHING_NEW", message="the server said so", details={})

    assert error.exit_code == 1
    assert error.message == "the server said so"


def test_a_server_error_keeps_the_details_for_the_renderer() -> None:
    error = ServerError(
        code="ALLOCATION_LIMIT_EXCEEDED", message="no room", details={"free_bytes": 1024}
    )

    assert error.exit_code == 5
    assert error.details["free_bytes"] == 1024


def test_munge_being_unavailable_is_exit_3_with_a_hint() -> None:
    error = AuthUnavailable("munged is not running")

    assert error.exit_code == 3
    assert "munge" in error.message.lower()


def test_a_transport_failure_is_exit_7() -> None:
    assert TransportError("connection refused").exit_code == 7


def test_a_usage_error_is_exit_2() -> None:
    assert UsageError("say what?").exit_code == 2


def test_every_cli_error_carries_a_message_and_an_exit_code() -> None:
    for error in (UsageError("x"), AuthUnavailable("x"), TransportError("x")):
        assert isinstance(error, CliError)
        assert error.message
        assert error.exit_code > 0
