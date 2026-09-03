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


class CliError(Exception):
    exit_code = GENERIC

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
        super().__init__(message)
