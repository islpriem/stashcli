"""stashcli — the STASH command-line client."""

from typing import Any

__all__ = ["__version__"]


def __getattr__(name: str) -> Any:
    """Read the version only when it is asked for: importing metadata costs 25 ms."""
    if name == "__version__":
        from importlib.metadata import version

        return version("stashcli")
    raise AttributeError(name)
