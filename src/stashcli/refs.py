"""Reference syntax.

Parsed only far enough to fill structured request fields: the leading slash decides
whether this is a path or a fileset name. No path is ever built here — the server returns
paths.
"""

import re
from dataclasses import dataclass

from stashcli.errors import UsageError

STORAGE_ID = re.compile(r"^[A-Z][A-Z0-9_-]{0,31}$")
FILESET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True, slots=True)
class PathRef:
    storage: str
    path: str

    def __str__(self) -> str:
        return f"{self.storage}:{self.path}"


@dataclass(frozen=True, slots=True)
class FilesetRef:
    storage: str
    name: str

    def __str__(self) -> str:
        return f"{self.storage}:{self.name}"


def parse_reference(text: str, *, default_storage: str | None = None) -> PathRef | FilesetRef:
    storage, separator, rest = text.partition(":")
    if not separator:
        return FilesetRef(_storage(default_storage, text), _name(text))
    if not rest:
        raise UsageError(f"{text!r} names no path or fileset after the colon")
    _check_storage(storage)
    return (
        PathRef(storage, _path(text, rest))
        if rest.startswith("/")
        else FilesetRef(storage, _name(rest))
    )


def _storage(default_storage: str | None, text: str) -> str:
    if default_storage is None:
        raise UsageError(
            f"{text!r} has no storage",
            hint="write STORAGE:name, pass --storage, or set a default storage in the config",
        )
    _check_storage(default_storage)
    return default_storage


def _check_storage(storage: str) -> str:
    if not STORAGE_ID.match(storage):
        raise UsageError(
            f"{storage!r} is not a storage id (uppercase letters, digits, - and _)"
        )
    return storage


def _name(name: str) -> str:
    if not FILESET_NAME.match(name):
        raise UsageError(f"{name!r} is not a fileset name: {FILESET_NAME.pattern}")
    return name


def _path(text: str, path: str) -> str:
    stripped = path.rstrip("/") or "/"
    segments = stripped.split("/")[1:] if stripped != "/" else []
    if any(segment in ("", ".", "..") for segment in segments):
        raise UsageError(f"{text!r} is not a plain path: empty, . and .. segments are refused")
    return stripped
