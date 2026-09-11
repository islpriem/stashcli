"""Failures and the exit codes they produce.

Command modules raise these; ``main.py`` is the only place that exits. Exit codes are a
contract: job scripts branch on them.
"""

from typing import Any

GENERIC = 1
USAGE = 2
AUTHENTICATION = 3
NOT_FOUND = 4
ALLOCATION = 5
CONFLICT = 6
UNAVAILABLE = 7
TRANSFER_FAILED = 8
INTERRUPTED = 130

_EXIT_CODES: dict[str, int] = {
    "INTERNAL": GENERIC,
    "INVALID_REQUEST": USAGE,
    "UNAUTHENTICATED": AUTHENTICATION,
    "NOT_FOUND": NOT_FOUND,
    "PATH_NOT_FOUND": NOT_FOUND,
    "FILESET_NOT_READY": NOT_FOUND,
    "ALLOCATION_LIMIT_EXCEEDED": ALLOCATION,
    "TOTAL_ALLOCATION_LIMIT_EXCEEDED": ALLOCATION,
    "STORAGE_FULL": ALLOCATION,
    "OVER_ALLOCATION": ALLOCATION,
    "TOO_MANY_FILESETS": ALLOCATION,
    "TOO_MANY_QUEUED": ALLOCATION,
    "CONFLICT": CONFLICT,
    "FILESET_EXISTS": CONFLICT,
    "SOURCE_MISMATCH": CONFLICT,
    "FORBIDDEN": CONFLICT,
    "PERMISSION_DENIED": CONFLICT,
    "INVALID_NAME": CONFLICT,
    "INVALID_PATH": CONFLICT,
    "NOT_A_SOURCE_STORAGE": CONFLICT,
    "NOT_A_CACHE_STORAGE": CONFLICT,
    "FLUSH_TARGET_REQUIRED": CONFLICT,
    "DAEMON_UNAVAILABLE": UNAVAILABLE,
    "STORAGE_DRAINED": UNAVAILABLE,
    "CONFIG_STALE": UNAVAILABLE,
}


def exit_code_for(code: str) -> int:
    """An unknown code is not a crash: it exits 1 and the server's message is printed."""
    return _EXIT_CODES.get(code, GENERIC)


_ADVICE = {
    "ALLOCATION_LIMIT_EXCEEDED": (
        "Release filesets you no longer need (stash fileset list), "
        "or ask an admin to raise your limit."
    ),
    "TOTAL_ALLOCATION_LIMIT_EXCEEDED": (
        "Release filesets on any cache (stash quota), or ask an admin to raise your limit."
    ),
    "STORAGE_FULL": "The storage itself is full; try another cache or wait.",
    "OVER_ALLOCATION": (
        # Growing the fileset would allocate, which is the thing being refused, so
        # resizing is not a way out of this one.
        "A fileset uses more than it reserved. Delete what is inside it, or release it "
        "(stash release), and it clears at the next usage check."
    ),
    "TOO_MANY_FILESETS": "Release a fileset you no longer need first.",
    "TOO_MANY_QUEUED": "Wait for one of your transfers to finish (stash status).",
    "FILESET_EXISTS": (
        "Pick another name, or refresh the existing fileset (stash warm --refresh)."
    ),
    "SOURCE_MISMATCH": "That name already holds another source; use a different name.",
    "UNAUTHENTICATED": "Check that munged is running on this node.",
    "STORAGE_DRAINED": "The storage is drained for maintenance; try again later.",
    "DAEMON_UNAVAILABLE": "The storage daemon is not reachable; try again later.",
}


def explain(details: dict[str, Any]) -> str | None:
    """The server's own numbers, said once, in the order a person reads them."""
    if "required_bytes" not in details:
        return None
    from stashcli.sizes import format_bytes

    where = details.get("storage") or "all caches"
    return (
        f"{format_bytes(int(details['required_bytes']))} needed · "
        f"{format_bytes(int(details.get('free_bytes', 0)))} free of "
        f"{format_bytes(int(details.get('limit_bytes', 0)))} on {where}"
    )


class CliError(Exception):
    exit_code = GENERIC
    prefix = "Error: "

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        self.message = message
        self.hint = hint
        super().__init__(message)


class UsageError(CliError):
    exit_code = USAGE


class AuthUnavailable(CliError):
    exit_code = AUTHENTICATION

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(
            f"MUNGE authentication is unavailable: {message}",
            hint=hint or "check that munged is running and its socket is readable",
        )


class Detached(CliError):
    """Not a failure: the user stopped watching, and the work carries on."""

    exit_code = INTERRUPTED
    prefix = ""


class StillRunning(CliError):
    """--wait reached its timeout. Nothing is wrong, but nothing is staged either:
    exiting 0 would let a job script start on data that has not arrived. There is no
    dedicated code for this, so the generic one is used."""

    exit_code = GENERIC
    prefix = ""


class Aborted(CliError):
    exit_code = INTERRUPTED


class NotFoundError(CliError):
    exit_code = NOT_FOUND


class TransportError(CliError):
    exit_code = UNAVAILABLE


class TransferFailed(CliError):
    exit_code = TRANSFER_FAILED


class ServerError(CliError):
    """The error envelope, with the server's own numbers kept for the renderer."""

    def __init__(self, *, code: str, message: str, details: dict[str, Any]) -> None:
        self.code = code
        self.details = details
        self.exit_code = exit_code_for(code)
        # The message stays exactly as the server wrote it; the code is added
        # where it is printed.
        super().__init__(message, hint=_ADVICE.get(code))
        self.numbers = explain(details)
