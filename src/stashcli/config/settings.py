"""Where the server URL and the default storage come from.

In order: the command line, the environment, the user config, the system config. Nothing
is guessed: a missing server or default storage is an error that says what to do.
"""

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stashcli.errors import UsageError

DEFAULT_TIMEOUT = 30.0
USER_CONFIG = Path("stash/config.toml")
SYSTEM_CONFIG = Path("/etc/stash/stashcli.toml")


@dataclass(frozen=True, slots=True)
class Settings:
    server: str
    storage: str | None
    timeout: float


def default_config_paths(env: Mapping[str, str], home: Path) -> list[Path]:
    config_home = (
        Path(env["XDG_CONFIG_HOME"]) if env.get("XDG_CONFIG_HOME") else home / ".config"
    )
    return [config_home / USER_CONFIG, SYSTEM_CONFIG]


def resolve_settings(
    *,
    server: str | None = None,
    storage: str | None = None,
    timeout: float | None = None,
    env: Mapping[str, str],
    config_paths: Sequence[Path],
) -> Settings:
    files = [_read(path) for path in config_paths if path.is_file()]
    resolved_server = server or env.get("STASH_SERVER") or _first("server", files, str)
    if not resolved_server:
        raise UsageError(
            "no STASH server is configured",
            hint='pass --server, set STASH_SERVER, or put server = "…" in the config',
        )
    return Settings(
        server=resolved_server.rstrip("/"),
        storage=storage or env.get("STASH_STORAGE") or _first("storage", files, str),
        timeout=timeout
        if timeout is not None
        else _first("timeout", files, float) or DEFAULT_TIMEOUT,
    )


def _read(path: Path) -> tuple[Path, dict[str, Any]]:
    try:
        return path, tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, OSError) as error:
        raise UsageError(f"{path} could not be read: {error}") from None


def _first[T](
    key: str, files: Sequence[tuple[Path, dict[str, Any]]], expected: type[T]
) -> T | None:
    for path, values in files:
        if key not in values:
            continue
        value = values[key]
        if expected is float and isinstance(value, int) and not isinstance(value, bool):
            value = float(value)
        if not isinstance(value, expected):
            raise UsageError(
                f"{path}: {key} must be a {expected.__name__}, not {type(value).__name__}"
            )
        return value
    return None
