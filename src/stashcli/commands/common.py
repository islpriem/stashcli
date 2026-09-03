"""What more than one command needs: turning an argument into a reference."""

from typing import TYPE_CHECKING

from stashcli.errors import UsageError
from stashcli.refs import FilesetRef, PathRef, parse_reference
from stashcli.runtime import Runtime

if TYPE_CHECKING:
    from stashcli.client.stash import StashClient

CACHE_ROLE = "cache"


def fileset_reference(runtime: Runtime, client: "StashClient", text: str) -> FilesetRef:
    """`STORAGE:name`, or a bare name when a default storage applies.

    On a bare name with no default the caller is told which storages they could have
    meant, asked from the server. The CLI never picks one.
    """
    try:
        reference = parse_reference(text, default_storage=runtime.settings.storage)
    except UsageError as error:
        if ":" in text:
            raise
        raise UsageError(error.message, hint=_candidates(client)) from None
    if isinstance(reference, PathRef):
        raise UsageError(
            f"{text!r} is a path; this command takes a fileset",
            hint="a fileset reference has no leading slash: STORAGE:name",
        )
    return reference


def _candidates(client: "StashClient") -> str:
    caches = [storage.id for storage in client.storages() if CACHE_ROLE in storage.roles]
    listed = ", ".join(caches) if caches else "none of the storages hold filesets"
    return f"name the storage (STORAGE:name), pass --storage, or configure one: {listed}"
