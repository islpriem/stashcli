"""What the shell offers while a user is typing.

These run in their own process, with no Runtime and no parsed command line. Two rules
follow: settings come from the environment and config files only, and nothing here ever
raises — a completion helper that fails takes the prompt with it, so every failure is an
empty list. A shell is waiting between keystrokes, so there is one attempt and a short
timeout.
"""

import os
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from stashcli.auth.provider import AuthProvider
    from stashcli.client.stash import StashClient

READY = "READY"
TIMEOUT = 2.0


def _config_paths() -> Sequence[Path]:
    from stashcli.config.settings import default_config_paths

    return default_config_paths(dict(os.environ), Path.home())


def _transport() -> "httpx.BaseTransport | None":  # pragma: no cover - replaced in tests
    """The real client talks to the network; tests put a MockTransport here."""
    return None


def _auth() -> "AuthProvider":
    """A completion is a request like any other, and needs a credential."""
    from stashcli.auth.munge import MungeAuthProvider

    return MungeAuthProvider()


def _client() -> "StashClient":
    from stashcli.client.stash import StashClient
    from stashcli.config.settings import resolve_settings

    settings = resolve_settings(env=dict(os.environ), config_paths=_config_paths())
    return StashClient(
        settings.server,
        _auth(),
        timeout=min(settings.timeout, TIMEOUT),
        transport=_transport(),
        attempts=1,
        on_warning=_say_nothing,
    )


def _say_nothing(message: str) -> None:
    """A version warning has nowhere to go while the shell is drawing a list."""


def _default_storage() -> str | None:
    from stashcli.config.settings import resolve_settings

    return resolve_settings(env=dict(os.environ), config_paths=_config_paths()).storage


def complete_storage(incomplete: str) -> list[str]:
    """Every storage whose id starts with what has been typed."""
    try:
        with _client() as client:
            names = [storage.id for storage in client.storages()]
    except Exception:
        return []
    return [name for name in names if name.lower().startswith(incomplete.lower())]


def complete_fileset(incomplete: str) -> list[str]:
    """Filesets a command would accept: STORAGE:name, or bare with a default storage."""
    try:
        default = _default_storage()
        with _client() as client:
            filesets = client.filesets(state=READY)
    except Exception:
        return []
    offered = [
        fileset.name if default and fileset.storage_id == default else fileset.reference
        for fileset in filesets
    ]
    return [name for name in offered if name.lower().startswith(incomplete.lower())]
